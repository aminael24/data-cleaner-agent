import json

from langgraph.graph import END, START, StateGraph

from agent.groq_client import (
    SYSTEM_PROMPT,
    call_agent_model,
    create_client,
)

from agent.state import AgentState

from agent.tools import (
    ToolRuntime,
    execute_tool,
)


# ============================================================
# CONFIG
# ============================================================

MAX_AGENT_TURNS = 10

# On évite de renvoyer des dizaines de milliers
# de caractères au LLM.
MAX_EVIDENCE_CHARS = 4200


# ============================================================
# ASSISTANT MESSAGE
# ============================================================

def _assistant_message_to_dict(
    message,
):

    payload = {
        "role":
            "assistant",

        "content":
            message.content
            or "",
    }


    tool_calls = (
        getattr(
            message,
            "tool_calls",
            None,
        )
        or []
    )


    if tool_calls:

        payload[
            "tool_calls"
        ] = []


        for tool_call in (
            tool_calls
        ):

            payload[
                "tool_calls"
            ].append(
                {
                    "id":
                        tool_call.id,

                    "type":
                        "function",

                    "function":
                        {
                            "name":
                                tool_call
                                .function
                                .name,

                            "arguments":
                                tool_call
                                .function
                                .arguments,
                        },
                }
            )


    return payload


# ============================================================
# COMPACT TOOL RESULT
# ============================================================

def _compact_tool_result(
    tool_name,
    result,
):
    """
    Réduit uniquement ce qui est envoyé au LLM.

    IMPORTANT :
    les outils continuent d'analyser
    le DataFrame complet.

    On réduit uniquement la représentation
    textuelle retournée au modèle.
    """

    if not isinstance(
        result,
        dict,
    ):

        return result


    # ========================================================
    # PROFILE DATASET
    # ========================================================

    if (
        tool_name
        ==
        "profile_dataset"
    ):

        compact_columns = []


        for column in (
            result.get(
                "columns",
                []
            )
            or []
        ):

            compact_column = {
                "name":
                    column.get(
                        "name"
                    ),

                "dtype":
                    column.get(
                        "dtype"
                    ),

                "missing_count":
                    column.get(
                        "missing_count",
                        0,
                    ),

                "unique_count":
                    column.get(
                        "unique_count",
                        0,
                    ),

                "whitespace_count":
                    column.get(
                        "whitespace_count",
                        0,
                    ),

                "null_like_count":
                    column.get(
                        "null_like_count",
                        0,
                    ),

                "numeric_candidate_ratio":
                    column.get(
                        "numeric_candidate_ratio",
                        0,
                    ),

                "date_candidate_ratio":
                    column.get(
                        "date_candidate_ratio",
                        0,
                    ),
            }


            # seulement quelques exemples
            samples = (
                column.get(
                    "sample_values",
                    []
                )
                or []
            )


            if samples:

                compact_column[
                    "sample_values"
                ] = samples[:3]


            # stats numériques utiles
            for key in (
                "min",
                "max",
                "mean",
                "negative_count",
            ):

                if key in column:

                    compact_column[
                        key
                    ] = column[
                        key
                    ]


            compact_columns.append(
                compact_column
            )


        return {
            "rows":
                result.get(
                    "rows",
                    0,
                ),

            "columns_count":
                result.get(
                    "columns_count",
                    0,
                ),

            "total_missing":
                result.get(
                    "total_missing",
                    0,
                ),

            "duplicate_rows":
                result.get(
                    "duplicate_rows",
                    0,
                ),

            "duplicate_rows_to_remove":
                result.get(
                    "duplicate_rows_to_remove",
                    0,
                ),

            "header_issues":
                (
                    result.get(
                        "header_issues",
                        []
                    )
                    or []
                )[:8],

            "columns":
                compact_columns,
        }


    # ========================================================
    # INSPECT COLUMN
    # ========================================================

    if (
        tool_name
        ==
        "inspect_column"
    ):

        compact = dict(
            result
        )


        compact[
            "sample_values"
        ] = (
            result.get(
                "sample_values",
                []
            )
            or []
        )[:8]


        top_values = (
            result.get(
                "top_values",
                {}
            )
            or {}
        )


        compact[
            "top_values"
        ] = dict(
            list(
                top_values.items()
            )[:6]
        )


        return compact


    # ========================================================
    # NUMERIC
    # ========================================================

    if (
        tool_name
        ==
        "detect_numeric_issues"
    ):

        compact = dict(
            result
        )


        compact[
            "examples_invalid"
        ] = (
            result.get(
                "examples_invalid",
                []
            )
            or []
        )[:5]


        compact[
            "examples_values"
        ] = (
            result.get(
                "examples_values",
                []
            )
            or []
        )[:6]


        return compact


    # ========================================================
    # DATE
    # ========================================================

    if (
        tool_name
        ==
        "detect_date_issues"
    ):

        compact = dict(
            result
        )


        compact[
            "examples_invalid"
        ] = (
            result.get(
                "examples_invalid",
                []
            )
            or []
        )[:5]


        compact[
            "examples_values"
        ] = (
            result.get(
                "examples_values",
                []
            )
            or []
        )[:6]


        return compact


    # ========================================================
    # TEXT
    # ========================================================

    if (
        tool_name
        ==
        "detect_text_anomalies"
    ):

        columns = []


        for column in (
            result.get(
                "columns",
                []
            )
            or []
        ):

            item = {
                "column":
                    column.get(
                        "column"
                    ),

                "whitespace_count":
                    column.get(
                        "whitespace_count",
                        0,
                    ),

                "null_like_count":
                    column.get(
                        "null_like_count",
                        0,
                    ),

                "case_variant_groups":
                    (
                        column.get(
                            "case_variant_groups",
                            []
                        )
                        or []
                    )[:4],

                "examples_whitespace":
                    (
                        column.get(
                            "examples_whitespace",
                            []
                        )
                        or []
                    )[:4],

                "examples_null_like":
                    (
                        column.get(
                            "examples_null_like",
                            []
                        )
                        or []
                    )[:4],
            }


            columns.append(
                item
            )


        return {
            "columns":
                columns
        }


    # ========================================================
    # DUPLICATES
    # ========================================================

    if (
        tool_name
        ==
        "find_duplicates"
    ):

        compact = dict(
            result
        )


        if (
            "examples"
            in compact
        ):

            compact[
                "examples"
            ] = (
                compact.get(
                    "examples",
                    []
                )
                or []
            )[:4]


        if (
            "exact_examples"
            in compact
        ):

            compact[
                "exact_examples"
            ] = (
                compact.get(
                    "exact_examples",
                    []
                )
                or []
            )[:3]


        if (
            "conflict_examples"
            in compact
        ):

            compact[
                "conflict_examples"
            ] = (
                compact.get(
                    "conflict_examples",
                    []
                )
                or []
            )[:3]


        return compact


    # ========================================================
    # EXTERNAL REFERENCE
    # ========================================================

    if (
        tool_name
        ==
        "verify_external_reference"
    ):

        compact = dict(
            result
        )


        compact[
            "corrections"
        ] = (
            result.get(
                "corrections",
                []
            )
            or []
        )[:15]


        return compact


    return result


# ============================================================
# TRACE -> COMPACT MEMORY
# ============================================================

def _build_evidence_memory(
    trace,
):
    """
    Transforme les anciens appels outils
    en mémoire compacte.

    Ainsi on ne renvoie pas toute la conversation
    Tool → Agent → Tool → Agent à chaque tour.
    """

    if not trace:

        return ""


    lines = [
        (
            "Evidence already gathered by tools. "
            "Do not repeat a tool unless necessary:"
        )
    ]


    for index, item in enumerate(
        trace,
        start=1,
    ):

        tool = str(
            item.get(
                "tool",
                "tool"
            )
        )


        arguments = (
            item.get(
                "arguments",
                {}
            )
            or {}
        )


        summary = str(
            item.get(
                "result_summary",
                ""
            )
        )


        arguments_text = (
            json.dumps(
                arguments,
                ensure_ascii=False,
                default=str,
            )
        )


        line = (
            f"{index}. {tool}"
            f"({arguments_text})"
            f" -> {summary}"
        )


        lines.append(
            line
        )


    memory = "\n".join(
        lines
    )


    if (
        len(memory)
        >
        MAX_EVIDENCE_CHARS
    ):

        # Garder surtout les appels récents.
        memory = (
            memory[
                -MAX_EVIDENCE_CHARS:
            ]
        )


        memory = (
            "Earlier evidence was compacted.\n"
            +
            memory
        )


    return memory


# ============================================================
# LATEST TOOL EXCHANGE
# ============================================================

def _latest_tool_exchange(
    messages,
):
    """
    Garde uniquement le DERNIER :

        assistant(tool_calls)
            +
        tool results

    Les anciens résultats passent dans
    _build_evidence_memory().
    """

    last_assistant_index = None


    for index in range(
        len(messages) - 1,
        -1,
        -1,
    ):

        message = (
            messages[
                index
            ]
        )


        if (
            message.get(
                "role"
            )
            ==
            "assistant"

            and

            message.get(
                "tool_calls"
            )
        ):

            last_assistant_index = (
                index
            )

            break


    if (
        last_assistant_index
        is None
    ):

        return []


    exchange = [
        messages[
            last_assistant_index
        ]
    ]


    for message in (
        messages[
            last_assistant_index + 1:
        ]
    ):

        if (
            message.get(
                "role"
            )
            ==
            "tool"
        ):

            exchange.append(
                message
            )


    return exchange


# ============================================================
# MODEL REQUEST MESSAGES
# ============================================================

def _build_request_messages(
    state,
):
    """
    Construit une requête Groq compacte.

    Au lieu de :

        system
        user
        agent
        tool
        agent
        tool
        agent
        tool
        ...

    on envoie :

        system
        user
        evidence compactée
        dernier échange tool
    """

    state_messages = list(
        state.get(
            "messages",
            []
        )
    )


    trace = list(
        state.get(
            "trace",
            []
        )
    )


    request_messages = [
        {
            "role":
                "system",

            "content":
                SYSTEM_PROMPT,
        },

        {
            "role":
                "user",

            "content":
                (
                    "Audit this dataset. "
                    "Use tools only when they add evidence. "
                    "The dataset stays local. "
                    "When enough evidence has been collected, "
                    "call submit_cleaning_plan exactly once."
                ),
        },
    ]


    evidence = (
        _build_evidence_memory(
            trace
        )
    )


    if evidence:

        request_messages.append(
            {
                "role":
                    "user",

                "content":
                    evidence,
            }
        )


    latest_exchange = (
        _latest_tool_exchange(
            state_messages
        )
    )


    request_messages.extend(
        latest_exchange
    )


    return request_messages


# ============================================================
# GRAPH
# ============================================================

def _build_graph(
    runtime: ToolRuntime,
):

    builder = StateGraph(
        AgentState
    )


    # ========================================================
    # AGENT NODE
    # ========================================================

    def agent_node(
        state: AgentState,
    ):

        messages = list(
            state.get(
                "messages",
                []
            )
        )


        iterations = int(
            state.get(
                "iterations",
                0,
            )
        )


        if (
            iterations
            >=
            MAX_AGENT_TURNS
        ):

            return {
                **state,

                "error":
                    (
                        "L'agent a atteint la limite "
                        "d'itérations sans soumettre "
                        "de plan."
                    ),
            }


        # IMPORTANT :
        # on n'envoie plus tout l'historique.
        request_messages = (
            _build_request_messages(
                state
            )
        )


        response = (
            call_agent_model(
                runtime.client,
                request_messages,
            )
        )


        assistant = (
            _assistant_message_to_dict(
                response
                .choices[0]
                .message
            )
        )


        messages.append(
            assistant
        )


        return {
            **state,

            "messages":
                messages,

            "iterations":
                iterations
                +
                1,
        }


    # ========================================================
    # TOOL NODE
    # ========================================================

    def tools_node(
        state: AgentState,
    ):

        messages = list(
            state.get(
                "messages",
                []
            )
        )


        trace = list(
            state.get(
                "trace",
                []
            )
        )


        plan = (
            state.get(
                "plan"
            )
        )


        error = (
            state.get(
                "error"
            )
        )


        if not messages:

            return {
                **state,
                "error":
                    "Aucun message agent disponible.",
            }


        assistant = (
            messages[-1]
        )


        tool_calls = (
            assistant.get(
                "tool_calls",
                []
            )
            or []
        )


        for call in (
            tool_calls
        ):

            function_data = (
                call.get(
                    "function",
                    {}
                )
            )


            name = str(
                function_data.get(
                    "name",
                    ""
                )
            )


            raw_arguments = (
                function_data.get(
                    "arguments",
                    "{}"
                )
                or "{}"
            )


            try:

                arguments = (
                    json.loads(
                        raw_arguments
                    )
                )

            except json.JSONDecodeError:

                arguments = {}


            try:

                full_result = (
                    execute_tool(
                        runtime,
                        name,
                        arguments,
                    )
                )


                if (
                    name
                    ==
                    "submit_cleaning_plan"
                ):

                    plan = (
                        full_result
                    )


                compact_result = (
                    _compact_tool_result(
                        name,
                        full_result,
                    )
                )


                compact_json = (
                    json.dumps(
                        compact_result,
                        ensure_ascii=False,
                        default=str,
                    )
                )


                trace.append(
                    {
                        "tool":
                            name,

                        "arguments":
                            arguments,

                        "result_summary":
                            compact_json[
                                :700
                            ],

                        "status":
                            "ok",
                    }
                )


                # Le modèle reçoit la version compacte.
                tool_content = (
                    compact_json
                )


            except Exception as exc:

                result = {
                    "error":
                        (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),

                    "tool":
                        name,
                }


                trace.append(
                    {
                        "tool":
                            name,

                        "arguments":
                            arguments,

                        "result_summary":
                            result[
                                "error"
                            ],

                        "status":
                            "error",
                    }
                )


                tool_content = (
                    json.dumps(
                        result,
                        ensure_ascii=False,
                    )
                )


                error = (
                    result[
                        "error"
                    ]
                )


            messages.append(
                {
                    "role":
                        "tool",

                    "tool_call_id":
                        call.get(
                            "id"
                        ),

                    "content":
                        tool_content,
                }
            )


        return {
            **state,

            "messages":
                messages,

            "trace":
                trace,

            "plan":
                plan,

            "error":
                error,
        }


    # ========================================================
    # RECOVERY
    # ========================================================

    def recovery_node(
        state: AgentState,
    ):

        messages = list(
            state.get(
                "messages",
                []
            )
        )


        messages.append(
            {
                "role":
                    "user",

                "content":
                    (
                        "Continue the audit. "
                        "Do not repeat tools unnecessarily. "
                        "When enough evidence exists, "
                        "call submit_cleaning_plan."
                    ),
            }
        )


        return {
            **state,

            "messages":
                messages,
        }


    # ========================================================
    # ROUTING
    # ========================================================

    def route_after_agent(
        state: AgentState,
    ):

        if (
            state.get(
                "error"
            )
            and
            int(
                state.get(
                    "iterations",
                    0,
                )
            )
            >=
            MAX_AGENT_TURNS
        ):

            return "end"


        messages = (
            state.get(
                "messages",
                []
            )
        )


        if not messages:

            return "end"


        last = (
            messages[-1]
        )


        if (
            last.get(
                "tool_calls"
            )
        ):

            return "tools"


        if (
            state.get(
                "plan"
            )
            is not None
        ):

            return "end"


        if (
            int(
                state.get(
                    "iterations",
                    0,
                )
            )
            >=
            MAX_AGENT_TURNS
        ):

            return "end"


        return "recovery"


    def route_after_tools(
        state: AgentState,
    ):

        if (
            state.get(
                "plan"
            )
            is not None
        ):

            return "end"


        if (
            int(
                state.get(
                    "iterations",
                    0,
                )
            )
            >=
            MAX_AGENT_TURNS
        ):

            return "end"


        return "agent"


    # ========================================================
    # BUILD
    # ========================================================

    builder.add_node(
        "agent",
        agent_node,
    )


    builder.add_node(
        "tools",
        tools_node,
    )


    builder.add_node(
        "recovery",
        recovery_node,
    )


    builder.add_edge(
        START,
        "agent",
    )


    builder.add_conditional_edges(
        "agent",

        route_after_agent,

        {
            "tools":
                "tools",

            "recovery":
                "recovery",

            "end":
                END,
        },
    )


    builder.add_conditional_edges(
        "tools",

        route_after_tools,

        {
            "agent":
                "agent",

            "end":
                END,
        },
    )


    builder.add_edge(
        "recovery",
        "agent",
    )


    return builder.compile()


# ============================================================
# RUN
# ============================================================

def run_data_cleaning_agent(
    df,
    api_key: str,
):

    client = (
        create_client(
            api_key
        )
    )


    runtime = ToolRuntime(
        df=df,
        client=client,
    )


    graph = (
        _build_graph(
            runtime
        )
    )


    initial_state: AgentState = {

        "messages": [
            {
                "role":
                    "system",

                "content":
                    SYSTEM_PROMPT,
            },

            {
                "role":
                    "user",

                "content":
                    (
                        "Audit this dataset. "
                        "Use tools dynamically based "
                        "on evidence. "
                        "The dataset stays local. "
                        "Submit one final cleaning plan."
                    ),
            },
        ],

        "trace":
            [],

        "plan":
            None,

        "error":
            None,

        "iterations":
            0,
    }


    final_state = (
        graph.invoke(
            initial_state
        )
    )


    if (
        final_state.get(
            "plan"
        )
        is None
        and
        not final_state.get(
            "error"
        )
    ):

        final_state[
            "error"
        ] = (
            "L'agent n'a pas soumis "
            "de plan de nettoyage."
        )


    return {
        "plan":
            final_state.get(
                "plan"
            ),

        "trace":
            final_state.get(
                "trace",
                []
            ),

        "error":
            final_state.get(
                "error"
            ),

        "iterations":
            final_state.get(
                "iterations",
                0,
            ),
    }