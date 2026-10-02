import os
import time

from groq import (
    Groq,
    BadRequestError,
)


# ============================================================
# MODEL
# ============================================================

MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b",
)


# ============================================================
# CONFIG
# ============================================================

MAX_TOOL_RETRIES = 2

MAX_OUTPUT_TOKENS = 1400


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = r"""
You are an autonomous Data Quality agent for heterogeneous TABULAR datasets.

The user may upload CSV, XLSX, or XLS files from sales, HR,
finance, IoT, research, logistics, or other domains.

Your job is to inspect evidence using tools, then submit
the smallest safe cleaning plan needed.


CORE RULES

1. Start with profile_dataset.

2. Use inspect_column and specialized tools only when they add useful evidence.

3. Do not invent anomalies.
   Every cleaning action must be supported by tool evidence.

4. If a tool reports zero affected values,
   DO NOT propose a cleaning action for that issue.

5. Never propose preventive cleaning such as stripping
   whitespace "just in case".

6. HIGH confidence requires concrete evidence that
   the proposed action is appropriate.

7. Missing values are not automatically errors.
   Do not invent imputations.

8. Outliers are not automatically wrong.

9. Negative values can be legitimate:
   returns, balances, corrections, deltas, etc.

   Only propose set_negative_to_null when context strongly
   proves negatives are invalid.

   Otherwise:
   - omit the action, or
   - use no_change with requires_review=true
     if human awareness is useful.

10. Use verify_external_reference only when correctness depends
    on an external factual reference.

    Examples:
    - country names/codes
    - currencies
    - geographic names
    - recognized companies
    - official identifiers
    - standards
    - externally verifiable vocabularies

11. Do NOT use external verification for local syntax problems:
    - whitespace
    - numeric parsing
    - dates
    - missing values
    - duplicates

12. External verification must be conservative.

    If uncertain:
    do not propose an automatic replacement.

13. A cleaning action can target:
    - one column using `column`
    - several columns using `columns`

14. Do not create no_change entries merely to say that
    nothing was found.

    no_change is reserved for a REAL detected issue where
    automatic correction is unsafe and human awareness matters.


DUPLICATE RULES

15. When checking duplicates by identifier/key columns,
    ALWAYS use the conflict information returned by find_duplicates.

16. If conflict_groups > 0,
    NEVER propose drop_duplicates_by_columns automatically.

17. Preserve conflicting rows.

    When useful, create a no_change action with:
    - requires_review=true
    - concise explanation of the conflict

18. Propose drop_duplicates_by_columns only when:

    safe_to_drop_by_key=true

19. Complete duplicate rows may use drop_duplicate_rows only when:

    duplicate_rows_to_remove > 0


EXECUTION RULES

20. Never generate or execute Python code.

    Only submit allow-listed structured actions.

21. Before finishing,
    call submit_cleaning_plan exactly once.


ALLOW-LISTED OPERATIONS

- normalize_column_names
- drop_empty_rows
- drop_empty_columns
- drop_duplicate_rows
- drop_duplicates_by_columns
- replace_null_like
- strip_whitespace
- normalize_case
- replace_values
- to_numeric
- to_datetime
- set_negative_to_null
- no_change


NUMERIC RULES

- "$389.54" must become numeric 389.54,
  never 38954.

- "793 USD" can become numeric 793.

- European decimal values such as "112,05"
  should use to_numeric.

- If a column mixes decimal comma and decimal point,
  to_numeric may still be used.

- The deterministic cleaning engine is responsible
  for preserving the actual decimal value.


PLAN QUALITY

- Prefer fewer, evidence-backed actions.

- requires_review=false only when the action is safe
  and evidence is strong.

- requires_review=true for ambiguous semantic changes.

- Include exact replacements for replace_values.

- Never repeat evidence already returned by tools
  inside long reason fields.

- Keep each reason concise:
  preferably under 100 characters.

- Do not write paragraphs inside tool arguments.

- Do not add redundant actions.

- If the same safe operation applies to several columns,
  prefer ONE action using `columns`
  instead of multiple almost-identical actions.

Example:

Instead of:

  replace_null_like(age)
  replace_null_like(salary)
  replace_null_like(status)

prefer:

  replace_null_like(
      columns=["age", "salary", "status"]
  )

when the same null token and same logic apply.

- The final submit_cleaning_plan tool call must contain
  valid COMPLETE JSON.

- Never leave strings, arrays, objects, or tool arguments unfinished.

""".strip()


# ============================================================
# TOOL SCHEMAS
# ============================================================

TOOL_SCHEMAS = [

    # ========================================================
    # PROFILE
    # ========================================================

    {
        "type": "function",

        "function": {

            "name":
                "profile_dataset",

            "description":
                (
                    "Profile the complete DataFrame locally "
                    "and return compact statistics for all columns."
                ),

            "parameters": {

                "type":
                    "object",

                "properties":
                    {},

                "additionalProperties":
                    False,
            },
        },
    },


    # ========================================================
    # INSPECT COLUMN
    # ========================================================

    {
        "type": "function",

        "function": {

            "name":
                "inspect_column",

            "description":
                (
                    "Inspect one column using the complete DataFrame: "
                    "type, missing count, unique count, samples, "
                    "frequent values and formatting signals."
                ),

            "parameters": {

                "type":
                    "object",

                "properties": {

                    "column": {
                        "type":
                            "string"
                    }
                },

                "required": [
                    "column"
                ],

                "additionalProperties":
                    False,
            },
        },
    },


    # ========================================================
    # NUMERIC
    # ========================================================

    {
        "type": "function",

        "function": {

            "name":
                "detect_numeric_issues",

            "description":
                (
                    "Analyze one column across all rows for numeric "
                    "parsing issues, currency symbols, decimal comma, "
                    "decimal point and invalid numeric strings."
                ),

            "parameters": {

                "type":
                    "object",

                "properties": {

                    "column": {
                        "type":
                            "string"
                    }
                },

                "required": [
                    "column"
                ],

                "additionalProperties":
                    False,
            },
        },
    },


    # ========================================================
    # DATE
    # ========================================================

    {
        "type": "function",

        "function": {

            "name":
                "detect_date_issues",

            "description":
                (
                    "Analyze one column for date parseability, "
                    "invalid values and likely date-format problems."
                ),

            "parameters": {

                "type":
                    "object",

                "properties": {

                    "column": {
                        "type":
                            "string"
                    }
                },

                "required": [
                    "column"
                ],

                "additionalProperties":
                    False,
            },
        },
    },


    # ========================================================
    # TEXT
    # ========================================================

    {
        "type": "function",

        "function": {

            "name":
                "detect_text_anomalies",

            "description":
                (
                    "Analyze one or more text columns for real "
                    "whitespace problems, placeholder/null-like "
                    "values and case variants."
                ),

            "parameters": {

                "type":
                    "object",

                "properties": {

                    "columns": {

                        "type":
                            "array",

                        "items": {
                            "type":
                                "string"
                        },

                        "minItems":
                            1,
                    }
                },

                "required": [
                    "columns"
                ],

                "additionalProperties":
                    False,
            },
        },
    },


    # ========================================================
    # DUPLICATES
    # ========================================================

    {
        "type": "function",

        "function": {

            "name":
                "find_duplicates",

            "description":
                (
                    "Find complete duplicate rows or analyze repeated "
                    "identifier/key values using the full DataFrame. "
                    "For key columns, distinguish exact duplicate groups "
                    "from conflicting groups where the same key has "
                    "different values in other columns. "
                    "Never assume repeated IDs are safe to drop."
                ),

            "parameters": {

                "type":
                    "object",

                "properties": {

                    "columns": {

                        "type":
                            "array",

                        "items": {
                            "type":
                                "string"
                        },
                    }
                },

                "additionalProperties":
                    False,
            },
        },
    },


    # ========================================================
    # EXTERNAL REFERENCE
    # ========================================================

    {
        "type": "function",

        "function": {

            "name":
                "verify_external_reference",

            "description":
                (
                    "Use Browser Search to conservatively verify "
                    "externally factual categorical/reference values "
                    "and return only high-confidence exact corrections. "
                    "Do not use for ordinary local cleaning."
                ),

            "parameters": {

                "type":
                    "object",

                "properties": {

                    "column": {
                        "type":
                            "string"
                    },

                    "values": {

                        "type":
                            "array",

                        "items": {
                            "type":
                                "string"
                        },

                        "minItems":
                            1,

                        "maxItems":
                            30,
                    },

                    "reference_context": {

                        "type":
                            "string",

                        "description":
                            (
                                "What the values represent and "
                                "the desired standard, if known."
                            ),
                    },
                },

                "required": [
                    "column",
                    "values",
                    "reference_context",
                ],

                "additionalProperties":
                    False,
            },
        },
    },


    # ========================================================
    # FINAL CLEANING PLAN
    # ========================================================

    {
        "type": "function",

        "function": {

            "name":
                "submit_cleaning_plan",

            "description":
                (
                    "Submit the final concise structured cleaning plan "
                    "after gathering enough evidence."
                ),

            "parameters": {

                "type":
                    "object",

                "properties": {

                    "actions": {

                        "type":
                            "array",

                        "items": {

                            "type":
                                "object",

                            "properties": {

                                # ============================
                                # OPERATION
                                # ============================

                                "operation": {

                                    "type":
                                        "string",

                                    "enum": [

                                        "normalize_column_names",

                                        "drop_empty_rows",

                                        "drop_empty_columns",

                                        "drop_duplicate_rows",

                                        "drop_duplicates_by_columns",

                                        "replace_null_like",

                                        "strip_whitespace",

                                        "normalize_case",

                                        "replace_values",

                                        "to_numeric",

                                        "to_datetime",

                                        "set_negative_to_null",

                                        "no_change",
                                    ],
                                },


                                # ============================
                                # TARGETS
                                # ============================

                                "column": {
                                    "type":
                                        "string"
                                },


                                "columns": {

                                    "type":
                                        "array",

                                    "items": {
                                        "type":
                                            "string"
                                    },
                                },


                                # ============================
                                # REPLACEMENTS
                                # ============================

                                "replacements": {

                                    "type":
                                        "array",

                                    "items": {

                                        "type":
                                            "object",

                                        "properties": {

                                            "old_value": {
                                                "type":
                                                    "string"
                                            },

                                            "new_value": {
                                                "type":
                                                    "string"
                                            },
                                        },

                                        "required": [
                                            "old_value",
                                            "new_value",
                                        ],

                                        "additionalProperties":
                                            False,
                                    },
                                },


                                # ============================
                                # NULL TOKENS
                                # ============================

                                "null_tokens": {

                                    "type":
                                        "array",

                                    "items": {
                                        "type":
                                            "string"
                                    },
                                },


                                # ============================
                                # CASE
                                # ============================

                                "case_mode": {

                                    "type":
                                        "string",

                                    "enum": [
                                        "none",
                                        "lower",
                                        "upper",
                                        "title",
                                    ],
                                },


                                # ============================
                                # DATE
                                # ============================

                                "dayfirst": {
                                    "type":
                                        "boolean"
                                },


                                # ============================
                                # NUMERIC
                                # ============================

                                "decimal_comma": {
                                    "type":
                                        "boolean"
                                },


                                # ============================
                                # EXPLANATION
                                # ============================

                                "reason": {

                                    "type":
                                        "string",

                                    # Encourage des raisons courtes.
                                    "maxLength":
                                        180,
                                },


                                # ============================
                                # CONFIDENCE
                                # ============================

                                "confidence": {

                                    "type":
                                        "string",

                                    "enum": [
                                        "high",
                                        "medium",
                                        "low",
                                    ],
                                },


                                # ============================
                                # HUMAN REVIEW
                                # ============================

                                "requires_review": {
                                    "type":
                                        "boolean"
                                },
                            },


                            "required": [

                                "operation",

                                "reason",

                                "confidence",

                                "requires_review",
                            ],


                            "additionalProperties":
                                False,
                        },
                    },
                },


                "required": [
                    "actions"
                ],


                "additionalProperties":
                    False,
            },
        },
    },
]


# ============================================================
# CREATE CLIENT
# ============================================================

def create_client(
    api_key: str,
) -> Groq:

    if not api_key:

        raise RuntimeError(
            "GROQ_API_KEY est absente."
        )


    return Groq(
        api_key=api_key
    )


# ============================================================
# CHECK TOOL JSON ERROR
# ============================================================

def _is_invalid_tool_json_error(
    exc: Exception,
) -> bool:
    """
    Détecte précisément l'erreur Groq :

    Failed to parse tool call arguments as JSON
    """

    error_text = str(
        exc
    )


    patterns = [

        (
            "Failed to parse tool call "
            "arguments as JSON"
        ),

        "tool_use_failed",

        "failed_generation",
    ]


    return any(
        pattern
        in error_text

        for pattern
        in patterns
    )


# ============================================================
# CALL AGENT MODEL
# ============================================================

def call_agent_model(
    client: Groq,
    messages: list[dict],
    max_retries: int = MAX_TOOL_RETRIES,
):
    """
    Appelle Groq.

    Si le modèle produit un tool call JSON incomplet :

        "reason": "Trailing

    Groq renvoie HTTP 400 avant que notre tool
    ne soit réellement exécuté.

    Dans ce cas uniquement, on refait automatiquement
    l'appel avec une instruction de concision.

    Cela ne double PAS l'exécution d'une action :
    le premier tool call n'a jamais été accepté.
    """

    working_messages = list(
        messages
    )


    last_error = None


    for attempt in range(
        max_retries + 1
    ):

        try:

            response = (
                client
                .chat
                .completions
                .create(

                    model=
                        MODEL,

                    messages=
                        working_messages,

                    tools=
                        TOOL_SCHEMAS,

                    tool_choice=
                        "auto",

                    # Pour la Data Quality :
                    # on préfère la stabilité.
                    temperature=
                        0,

                    # Assez grand pour un plan complet,
                    # mais limité pour éviter des sorties
                    # inutilement longues.
                    max_tokens=
                        MAX_OUTPUT_TOKENS,
                )
            )


            return response


        except BadRequestError as exc:

            last_error = exc


            # ------------------------------------------------
            # Autre HTTP 400 :
            # ne surtout pas le masquer.
            # ------------------------------------------------

            if not _is_invalid_tool_json_error(
                exc
            ):

                raise


            # ------------------------------------------------
            # Plus de retry disponible
            # ------------------------------------------------

            if (
                attempt
                >=
                max_retries
            ):

                raise RuntimeError(
                    (
                        "Groq n'a pas réussi à produire "
                        "des arguments JSON valides pour "
                        "le tool call après "
                        f"{max_retries + 1} tentative(s)."
                    )
                ) from exc


            # ------------------------------------------------
            # RETRY
            # ------------------------------------------------

            retry_instruction = {
                "role":
                    "user",

                "content":
                    (
                        "Your previous tool call could not be parsed "
                        "because its JSON arguments were incomplete "
                        "or invalid. Retry the SAME intended step now. "
                        "Return a concise valid tool call. "
                        "Use short reason strings. "
                        "Merge identical operations across multiple "
                        "columns when possible. "
                        "Do not add explanations outside the tool call. "
                        "Ensure every JSON string, array and object "
                        "is fully closed."
                    ),
            }


            working_messages = [
                *messages,
                retry_instruction,
            ]


            # Très petite pause.
            time.sleep(
                0.35
            )


    # Sécurité Python.
    if last_error:

        raise last_error


    raise RuntimeError(
        "Échec inattendu de l'appel Groq."
    )