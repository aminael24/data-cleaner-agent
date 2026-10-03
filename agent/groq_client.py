import json
import os
import re
import time
from collections import deque

from groq import APIStatusError, BadRequestError, Groq, RateLimitError


# ============================================================
# MODEL / CONFIG
# ============================================================

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

MAX_TOOL_RETRIES = int(os.getenv("GROQ_TOOL_RETRIES", "2"))
MAX_RATE_LIMIT_RETRIES = int(os.getenv("GROQ_RATE_RETRIES", "3"))

# Sortie max réservée. Avec gpt-oss, le raisonnement compte dans cette limite.
MAX_OUTPUT_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1500"))

REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low").strip()

# Limite Groq du compte (TPM). Marge de sécurité : jamais plus de 85 % par minute.
TPM_LIMIT = int(os.getenv("GROQ_TPM_LIMIT", "8000"))
TPM_SAFETY = float(os.getenv("GROQ_TPM_SAFETY", "0.85"))


# ============================================================
# SYSTEM PROMPT (volontairement court : il est renvoyé à chaque appel)
# ============================================================

SYSTEM_PROMPT = r"""
You are the SEMANTIC REVIEWER of a Data Quality agent.

A deterministic engine has ALREADY built a safe baseline cleaning plan that covers every
mechanical anomaly (spaces, null markers, case, typos, numbers, dates, duplicates, negatives).
It has no world knowledge. You do. You receive BASELINE (its actions) and CATEGORICAL FORMS
(the values that remain after the baseline).

YOUR JOB
1. Find forms that mean the same thing but are written differently:
   ISO codes (CA = Canada), translations (Italie = Italy), abbreviations,
   long/short names (United Kingdom = UK), synonyms (M = Male).
2. Return ONLY the extra actions needed, as replace_values:
   - old_value copied EXACTLY from the forms list,
   - new_value = the dominant canonical form already present in the data,
   - never map a form that is already canonical, never invent a new value.
3. Call submit_cleaning_plan exactly ONCE. If nothing needs adding, submit {"actions": []}.

RULES
- Never repeat baseline actions. Never use to_numeric on ids/phones. Never impute.
- Never delete rows and never null out values: only replace_values on categorical forms.
- requires_review=false only for unambiguous mappings (CA -> Canada). Ambiguous -> true.
- reason under 100 characters. Valid, complete JSON.
- Inspection tools are optional; submit_cleaning_plan is mandatory, even for actions=[].
- Use inspect_column for evidence. verify_external_reference only if truly
  unsure about a reference value (slow and costly).
""".strip()


# ============================================================
# TOOL SCHEMAS (4 outils seulement : moins de tokens à chaque appel)
# ============================================================

def _fn(name, description, properties, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                **({"required": required} if required else {}),
                "additionalProperties": False,
            },
        },
    }


_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": _STR}

# Le LLM ne peut proposer que des opérations non destructrices.
# (set_negative_to_null et les suppressions de lignes sont gérées uniquement par Python.)
_OPERATIONS = ["replace_values"]

TOOL_SCHEMAS = [
    _fn("inspect_column", "Inspect one full column: counts, samples, frequent values.", {"column": _STR}, ["column"]),
    _fn("find_duplicates", "Analyze full-row duplicates or repeated key values.", {"columns": _STR_LIST}),
    _fn(
        "verify_external_reference",
        "Web-verify externally factual categorical values; returns only high-confidence replacements.",
        {
            "column": _STR,
            "values": {**_STR_LIST, "minItems": 1, "maxItems": 20},
            "reference_context": _STR,
        },
        ["column", "values", "reference_context"],
    ),
    _fn(
        "submit_cleaning_plan",
        "Submit ONLY the extra semantic actions (merged with the baseline plan automatically).",
        {
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string", "enum": _OPERATIONS},
                        "column": _STR,
                        "columns": _STR_LIST,
                        "replacements": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"old_value": _STR, "new_value": _STR},
                                "required": ["old_value", "new_value"],
                                "additionalProperties": False,
                            },
                        },
                        "reason": {"type": "string", "maxLength": 120},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "requires_review": {"type": "boolean"},
                    },
                    "required": ["operation", "reason", "confidence", "requires_review"],
                    "additionalProperties": False,
                },
            }
        },
        ["actions"],
    ),
]

_TOOLS_TOKENS = len(json.dumps(TOOL_SCHEMAS)) // 3


# ============================================================
# BUDGET TPM GLISSANT
# ============================================================

_usage: deque = deque()  # (timestamp, tokens) sur 60 s


def estimate_tokens(messages: list[dict]) -> int:
    """Estimation prudente (~3 caractères / token) + schémas d'outils + sortie réservée."""
    chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
    return chars // 3 + _TOOLS_TOKENS + MAX_OUTPUT_TOKENS


def _used_last_minute(now: float) -> int:
    while _usage and now - _usage[0][0] > 60:
        _usage.popleft()
    return sum(tokens for _, tokens in _usage)


def _wait_for_budget(estimated: int) -> None:
    budget = int(TPM_LIMIT * TPM_SAFETY)
    if estimated > budget:
        raise RuntimeError(
            f"Requête trop grosse pour le quota ({estimated} tokens estimés > {budget}). "
            "Réduisez les données envoyées ou augmentez GROQ_TPM_LIMIT."
        )

    while True:
        now = time.monotonic()
        if _used_last_minute(now) + estimated <= budget:
            return
        oldest = _usage[0][0] if _usage else now
        time.sleep(max(0.5, 60 - (now - oldest) + 0.25))


def _record_usage(response, estimated: int) -> None:
    usage = getattr(response, "usage", None)
    tokens = getattr(usage, "total_tokens", None) or estimated
    _usage.append((time.monotonic(), int(tokens)))


def _retry_after_seconds(exc: Exception) -> float:
    match = re.search(r"try again in ([\d.]+)\s*(ms|s|m)\b", str(exc))
    if not match:
        return 8.0
    value, unit = float(match.group(1)), match.group(2)
    return value / 1000 if unit == "ms" else value * 60 if unit == "m" else value


# ============================================================
# CLIENT
# ============================================================

def create_client(api_key: str) -> Groq:
    if not api_key:
        raise RuntimeError("GROQ_API_KEY est absente.")
    return Groq(api_key=api_key)


def _is_invalid_tool_json_error(exc: Exception) -> bool:
    text = str(exc)
    return any(
        marker in text
        for marker in (
            "Failed to parse tool call arguments as JSON",
            "tool_use_failed",
            "failed_generation",
        )
    )


# ============================================================
# CALL MODEL
# ============================================================

def call_agent_model(client: Groq, messages: list[dict], max_retries: int = MAX_TOOL_RETRIES, *, force_submission: bool = False):
    """
    Appelle Groq en respectant le budget TPM.

    - attend avant l'appel si la dernière minute est déjà bien remplie ;
    - 429 : patiente le délai indiqué par Groq puis réessaie ;
    - 413 : requête trop grosse, inutile de réessayer (le plan de base reste valable) ;
    - JSON de tool call invalide : réessaie avec une consigne de concision.
    - exige un appel d'outil ; lors d'une reprise / au dernier tour, exige la soumission.
    """
    working_messages = list(messages)
    json_attempt = 0
    rate_attempt = 0

    while True:
        estimated = estimate_tokens(working_messages)
        _wait_for_budget(estimated)

        kwargs = {
            "model": MODEL,
            "messages": working_messages,
            "tools": TOOL_SCHEMAS,
            "tool_choice": (
                {"type": "function", "function": {"name": "submit_cleaning_plan"}}
                if force_submission else "required"
            ),
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        if REASONING_EFFORT:
            kwargs["extra_body"] = {"reasoning_effort": REASONING_EFFORT}

        try:
            response = client.chat.completions.create(**kwargs)
            _record_usage(response, estimated)
            return response

        except RateLimitError as exc:
            _usage.append((time.monotonic(), estimated))
            rate_attempt += 1
            if rate_attempt > MAX_RATE_LIMIT_RETRIES:
                raise
            time.sleep(min(_retry_after_seconds(exc) + 0.5, 65))

        except BadRequestError as exc:
            if not _is_invalid_tool_json_error(exc):
                raise
            json_attempt += 1
            if json_attempt > max_retries:
                raise RuntimeError(
                    "Groq n'a pas réussi à produire un tool call JSON valide après "
                    f"{max_retries + 1} tentative(s)."
                ) from exc
            working_messages = [
                *messages,
                {
                    "role": "user",
                    "content": (
                        "Your previous tool call JSON was invalid or incomplete. Retry the SAME step "
                        "with fully closed valid JSON and very short reasons."
                    ),
                },
            ]
            time.sleep(0.35)

        except APIStatusError as exc:
            if getattr(exc, "status_code", None) == 413:
                raise RuntimeError(
                    "Groq refuse la requête (413, trop de tokens pour le quota par minute)."
                ) from exc
            raise
