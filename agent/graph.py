from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.baseline import build_baseline, finalize_plan, summarize_actions
from agent.groq_client import SYSTEM_PROMPT, call_agent_model, create_client
from agent.preaudit import build_requirements, digest_summary, scan_dataset
from agent.state import AgentState
from agent.tools import ToolRuntime, execute_tool


# ============================================================
# CONFIG
# ============================================================

MAX_AGENT_TURNS = 5          # le LLM n'a plus qu'une petite revue sémantique à faire
MAX_EVIDENCE_CHARS = 2500
MEMORY_RESULT_CHARS = 800
UI_RESULT_CHARS = 800

TASK_MESSAGE = (
    "Review CATEGORICAL FORMS below. Submit ONLY extra replace_values actions for synonyms, "
    "codes or translations that the baseline cannot know. Empty list if nothing is needed."
)


# ============================================================
# HELPERS
# ============================================================

def _assistant_message_to_dict(message) -> dict:
    payload = {"role": "assistant", "content": message.content or ""}
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in tool_calls
        ]
    return payload


def _head(value, n):
    return (value or [])[:n]


def _compact_tool_result(tool_name: str, result: Any):
    if not isinstance(result, dict):
        return result

    compact = dict(result)

    if tool_name == "inspect_column":
        compact["sample_values"] = _head(result.get("sample_values"), 6)
        compact["top_values"] = dict(list((result.get("top_values") or {}).items())[:8])
    elif tool_name == "find_duplicates":
        for key, limit in (("examples", 2), ("exact_examples", 2), ("conflict_examples", 2)):
            if key in compact:
                compact[key] = _head(compact.get(key), limit)
    elif tool_name == "verify_external_reference":
        compact["corrections"] = _head(result.get("corrections"), 20)

    return compact


def _build_evidence_memory(trace: list[dict]) -> str:
    lines: list[str] = []
    for item in trace or []:
        if item.get("tool") in ("scan_all_columns", "baseline_plan", "coverage_check", "semantic_review"):
            continue
        if not item.get("memory_summary"):
            continue
        args = json.dumps(item.get("arguments", {}) or {}, ensure_ascii=False, separators=(",", ":"))
        lines.append(f"{len(lines) + 1}. {item.get('tool')}({args}) -> {item['memory_summary']}")

    if not lines:
        return ""

    memory = "\n".join(lines)
    if len(memory) > MAX_EVIDENCE_CHARS:
        memory = memory[-MAX_EVIDENCE_CHARS:]
    return "TOOL EVIDENCE ALREADY GATHERED:\n" + memory


def _latest_tool_exchange(messages: list[dict]) -> list[dict]:
    last_index = None
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "assistant" and messages[index].get("tool_calls"):
            last_index = index
            break
    if last_index is None:
        return []
    exchange = [messages[last_index]]
    exchange.extend(m for m in messages[last_index + 1:] if m.get("role") == "tool")
    return exchange


def _build_request_messages(state: AgentState) -> list[dict]:
    baseline_lines = summarize_actions(state.get("baseline_actions", []))
    forms = json.dumps(state.get("open_decisions", {}), ensure_ascii=False, separators=(",", ":"))

    request = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": TASK_MESSAGE},
        {"role": "user", "content": "BASELINE (already in the plan):\n" + "\n".join(baseline_lines)},
        {"role": "user", "content": "CATEGORICAL FORMS (column -> form: count):\n" + forms},
    ]

    evidence = _build_evidence_memory(state.get("trace", []))
    if evidence:
        request.append({"role": "user", "content": evidence})

    request.extend(_latest_tool_exchange(list(state.get("messages", []))))
    # Les anciens échanges sont compactés, mais la dernière consigne de reprise
    # doit rester dans la requête réellement envoyée au modèle.
    messages = list(state.get("messages", []))
    if messages and messages[-1].get("role") == "user":
        request.append(messages[-1])
    if state.get("force_submission"):
        request.append({
            "role": "user",
            "content": (
                'Finish the semantic review now by calling submit_cleaning_plan. '
                'If no extra mappings are justified, submit {"actions": []}. '
                'Do not repeat inspections or return a plain-text conclusion.'
            ),
        })
    return request


# ============================================================
# GRAPH
# ============================================================

def _build_graph(runtime: ToolRuntime):
    builder = StateGraph(AgentState)

    def agent_node(state: AgentState):
        messages = list(state.get("messages", []))
        iterations = int(state.get("iterations", 0))
        force_submission = bool(state.get("force_submission")) or iterations >= MAX_AGENT_TURNS - 1

        try:
            request_state = {**state, "force_submission": force_submission}
            response = call_agent_model(
                runtime.client, _build_request_messages(request_state),
                force_submission=force_submission,
            )
        except Exception as exc:  # quota Groq, JSON invalide... : le plan de base reste valable
            return {**state, "llm_error": f"{type(exc).__name__}: {exc}"}

        messages.append(_assistant_message_to_dict(response.choices[0].message))
        return {**state, "messages": messages, "iterations": iterations + 1}

    def tools_node(state: AgentState):
        messages = list(state.get("messages", []))
        trace = list(state.get("trace", []))
        plan = state.get("plan")
        requirements = state.get("requirements", []) or []
        identifier_columns = (state.get("findings") or {}).get("identifier_columns", [])

        calls = list(messages[-1].get("tool_calls", []) or []) if messages else []
        # Les outils d'inspection d'abord, la soumission du plan en dernier.
        calls.sort(key=lambda c: c.get("function", {}).get("name") == "submit_cleaning_plan")

        for call in calls:
            function_data = call.get("function", {})
            name = str(function_data.get("name", ""))

            try:
                arguments = json.loads(function_data.get("arguments", "{}") or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("Les arguments de l'outil doivent être un objet JSON.")
                if name == "submit_cleaning_plan":
                    # Ne pas transformer un JSON cassé ou un champ absent en
                    # fausse revue réussie avec une liste vide.
                    llm_actions = arguments.get("actions")
                    if not isinstance(llm_actions, list) or any(not isinstance(a, dict) for a in llm_actions):
                        raise ValueError("submit_cleaning_plan doit contenir une liste actions valide.")
                    final, info = finalize_plan(
                        state.get("baseline_actions", []), llm_actions, requirements, identifier_columns
                    )
                    plan = {"actions": final}

                    trace.append({
                        "tool": "semantic_review",
                        "arguments": {"actions_proposed": len(llm_actions)},
                        "result_summary": (
                            f"{info['llm_actions_kept']} action(s) sémantique(s) retenue(s) · "
                            f"plan final : {len(final)} actions"
                        ),
                        "memory_summary": "",
                        "status": "ok",
                    })
                    trace.append({
                        "tool": "coverage_check",
                        "arguments": {},
                        "result_summary": (
                            "Toutes les anomalies détectées sont couvertes."
                            if not info["auto_flagged"]
                            else f"{info['auto_flagged']} anomalie(s) signalée(s) en revue humaine automatiquement."
                        ),
                        "memory_summary": "",
                        "status": "ok" if not info["auto_flagged"] else "warning",
                    })
                    tool_content = json.dumps({"status": "accepted"})

                else:
                    full_result = execute_tool(runtime, name, arguments)
                    compact_json = json.dumps(
                        _compact_tool_result(name, full_result),
                        ensure_ascii=False, default=str, separators=(",", ":"),
                    )
                    trace.append({
                        "tool": name,
                        "arguments": arguments,
                        "result_summary": compact_json[:UI_RESULT_CHARS],
                        "memory_summary": compact_json[:MEMORY_RESULT_CHARS],
                        "status": "ok",
                    })
                    tool_content = compact_json

            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                trace.append({
                    "tool": name, "arguments": {"raw_arguments": function_data.get("arguments")},
                    "result_summary": message, "memory_summary": message, "status": "error",
                })
                tool_content = json.dumps({"error": message, "tool": name}, ensure_ascii=False)

            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": tool_content})

        return {**state, "messages": messages, "trace": trace, "plan": plan}

    def recovery_node(state: AgentState):
        messages = list(state.get("messages", []))
        messages.append({
            "role": "user",
            "content": "Call submit_cleaning_plan now (an empty actions list is fine).",
        })
        return {**state, "messages": messages, "force_submission": True}

    def _limit_reached(state: AgentState) -> bool:
        return int(state.get("iterations", 0)) >= MAX_AGENT_TURNS

    def route_after_agent(state: AgentState):
        if state.get("llm_error"):
            return "end"
        messages = state.get("messages", [])
        if not messages:
            return "end"
        if messages[-1].get("tool_calls"):
            # Une soumission au dernier tour doit encore être exécutée.
            return "tools"
        if _limit_reached(state):
            return "end"
        return "recovery"

    def route_after_tools(state: AgentState):
        if state.get("plan") is not None or _limit_reached(state):
            return "end"
        return "agent"

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("recovery", recovery_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "recovery": "recovery", "end": END})
    builder.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "end": END})
    builder.add_edge("recovery", "agent")

    return builder.compile()


# ============================================================
# RUN
# ============================================================

def run_data_cleaning_agent(df, api_key: str) -> dict:
    # 1) Scan déterministe de TOUTES les colonnes (aucun appel LLM).
    findings = scan_dataset(df)
    requirements = build_requirements(findings)

    # 2) Plan de base déterministe : couvre toutes les anomalies mécaniques.
    baseline = build_baseline(df, findings)
    identifier_columns = findings.get("identifier_columns", [])

    trace: list[dict] = [
        {
            "tool": "scan_all_columns",
            "arguments": {},
            "result_summary": digest_summary(findings, requirements),
            "memory_summary": "",
            "status": "ok",
        },
        *baseline["trace"],
    ]

    plan = None
    error = None
    iterations = 0

    # 3) Revue sémantique par le LLM (petite requête). Ignorée s'il n'y a rien à lui demander.
    if baseline["open_decisions"]:
        client = create_client(api_key)
        runtime = ToolRuntime(df=df, client=client)
        graph = _build_graph(runtime)

        final_state = graph.invoke({
            "messages": [],
            "trace": trace,
            "plan": None,
            "error": None,
            "iterations": 0,
            "findings": findings,
            "requirements": requirements,
            "rejections": 0,
            "baseline_actions": baseline["actions"],
            "open_decisions": baseline["open_decisions"],
            "llm_error": None,
            "force_submission": False,
        })

        trace = final_state.get("trace", trace)
        plan = final_state.get("plan")
        iterations = final_state.get("iterations", 0)

        if plan is None:
            reason = final_state.get("llm_error") or (
                f"aucune soumission valide de submit_cleaning_plan après {iterations} tour(s) ; "
                "la revue sémantique n'a pas été finalisée"
            )
            trace.append({
                "tool": "semantic_review",
                "arguments": {},
                "result_summary": f"Revue sémantique indisponible ({reason[:300]}) — plan de base conservé.",
                "memory_summary": "",
                "status": "warning",
            })
    else:
        trace.append({
            "tool": "semantic_review",
            "arguments": {},
            "result_summary": "Aucune décision sémantique nécessaire.",
            "memory_summary": "",
            "status": "ok",
        })

    # 4) Plan final = plan de base (+ décisions du LLM si disponibles) + filet de sécurité.
    if plan is None:
        final, info = finalize_plan(baseline["actions"], [], requirements, identifier_columns)
        plan = {"actions": final}
        if info["auto_flagged"]:
            trace.append({
                "tool": "coverage_check",
                "arguments": {},
                "result_summary": f"{info['auto_flagged']} anomalie(s) signalée(s) en revue humaine automatiquement.",
                "memory_summary": "",
                "status": "warning",
            })

    return {
        "plan": plan,
        "trace": trace,
        "error": error,
        "iterations": iterations,
        "coverage_requirements": requirements,
    }
