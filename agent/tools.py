import json
import re
from dataclasses import dataclass

import pandas as pd

from agent.groq_client import MODEL
from core.audit import NULL_LIKE, profile_dataset


@dataclass
class ToolRuntime:
    df: pd.DataFrame
    client: object


def _ensure_column(df: pd.DataFrame, column: str):
    if column not in df.columns:
        raise ValueError(f"Colonne inconnue : {column}")


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def profile_dataset_tool(runtime: ToolRuntime, **_):
    return profile_dataset(runtime.df)


def inspect_column_tool(runtime: ToolRuntime, column: str):
    _ensure_column(runtime.df, column)
    series = runtime.df[column]
    text = series.astype("string")
    non_null = series.dropna()

    top_values = (
        non_null.astype(str)
        .value_counts(dropna=False)
        .head(12)
        .to_dict()
    )

    result = {
        "column": column,
        "dtype": str(series.dtype),
        "rows": int(len(series)),
        "missing_count": int(series.isna().sum()),
        "unique_count": int(series.nunique(dropna=True)),
        "whitespace_count": int((text.notna() & (text != text.str.strip())).fillna(False).sum()),
        "top_values": {str(k): int(v) for k, v in top_values.items()},
        "sample_values": non_null.astype(str).drop_duplicates().head(10).tolist(),
    }

    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        result.update({
            "min": None if numeric.dropna().empty else float(numeric.min()),
            "max": None if numeric.dropna().empty else float(numeric.max()),
            "mean": None if numeric.dropna().empty else float(numeric.mean()),
            "negative_count": int((numeric < 0).fillna(False).sum()),
        })

    return result


def detect_numeric_issues_tool(runtime: ToolRuntime, column: str):
    _ensure_column(runtime.df, column)
    series = runtime.df[column]
    values = series.dropna().astype(str).str.strip()

    if values.empty:
        return {
            "column": column,
            "non_null_count": 0,
            "parseable_count": 0,
            "invalid_count": 0,
            "decimal_comma_count": 0,
            "decimal_point_count": 0,
            "currency_or_text_affix_count": 0,
            "examples_invalid": [],
        }

    numeric_chars = values.str.replace(r"[^0-9,\.\-]", "", regex=True)
    decimal_comma_mask = values.str.match(r"^\s*[-+]?\d+,\d+\s*$", na=False)
    decimal_point_mask = values.str.match(r"^\s*[-+]?\d+\.\d+\s*$", na=False)
    affix_mask = values.str.contains(r"[^0-9,\.\-\s]", regex=True, na=False)

    normalized = numeric_chars.copy()
    both = normalized.str.contains(",", regex=False) & normalized.str.contains(".", regex=False)
    euro_both = both & (normalized.str.rfind(",") > normalized.str.rfind("."))
    us_both = both & ~euro_both
    normalized.loc[euro_both] = (
        normalized.loc[euro_both]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    normalized.loc[us_both] = normalized.loc[us_both].str.replace(",", "", regex=False)

    only_comma = normalized.str.contains(",", regex=False) & ~normalized.str.contains(".", regex=False)
    normalized.loc[only_comma] = normalized.loc[only_comma].str.replace(",", ".", regex=False)

    converted = pd.to_numeric(normalized, errors="coerce")
    invalid_mask = converted.isna() & values.ne("")

    return {
        "column": column,
        "non_null_count": int(len(values)),
        "parseable_count": int(converted.notna().sum()),
        "invalid_count": int(invalid_mask.sum()),
        "decimal_comma_count": int(decimal_comma_mask.sum()),
        "decimal_point_count": int(decimal_point_mask.sum()),
        "currency_or_text_affix_count": int(affix_mask.sum()),
        "examples_invalid": values[invalid_mask].drop_duplicates().head(12).tolist(),
        "examples_values": values.drop_duplicates().head(12).tolist(),
        "suggest_decimal_comma": bool(decimal_comma_mask.sum() > decimal_point_mask.sum()),
    }


def detect_date_issues_tool(runtime: ToolRuntime, column: str):
    _ensure_column(runtime.df, column)
    series = runtime.df[column]
    values = series.dropna().astype(str).str.strip()

    if values.empty:
        return {
            "column": column,
            "non_null_count": 0,
            "parseable_count": 0,
            "invalid_count": 0,
            "examples_invalid": [],
        }

    sample_for_guess = values.head(2000)
    parsed_monthfirst = pd.to_datetime(sample_for_guess, errors="coerce", format="mixed", dayfirst=False)
    parsed_dayfirst = pd.to_datetime(sample_for_guess, errors="coerce", format="mixed", dayfirst=True)

    monthfirst_count = int(parsed_monthfirst.notna().sum())
    dayfirst_count = int(parsed_dayfirst.notna().sum())
    dayfirst = dayfirst_count > monthfirst_count

    parsed = pd.to_datetime(values, errors="coerce", format="mixed", dayfirst=dayfirst)
    invalid_mask = parsed.isna()

    return {
        "column": column,
        "non_null_count": int(len(values)),
        "parseable_count": int(parsed.notna().sum()),
        "invalid_count": int(invalid_mask.sum()),
        "dayfirst_recommended": bool(dayfirst),
        "examples_invalid": values[invalid_mask].drop_duplicates().head(12).tolist(),
        "examples_values": values.drop_duplicates().head(12).tolist(),
    }


def detect_text_anomalies_tool(runtime: ToolRuntime, columns: list[str]):
    result = []

    for column in columns:
        _ensure_column(runtime.df, column)
        series = runtime.df[column]
        text = series.astype("string")
        normalized = text.str.strip()

        whitespace_mask = (text.notna() & (text != normalized)).fillna(False)
        null_like_mask = (
            text.notna()
            & normalized.str.casefold().isin(NULL_LIKE)
        ).fillna(False)

        case_variants = {}
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            groups = {}
            unique_values = normalized.dropna().drop_duplicates().head(500)
            for value in unique_values:
                key = str(value).casefold()
                groups.setdefault(key, []).append(str(value))
            case_variants = {
                key: values
                for key, values in groups.items()
                if len(set(values)) > 1
            }

        result.append({
            "column": column,
            "whitespace_count": int(whitespace_mask.sum()),
            "null_like_count": int(null_like_mask.sum()),
            "case_variant_groups": list(case_variants.values())[:12],
            "examples_whitespace": text[whitespace_mask].dropna().drop_duplicates().head(8).tolist(),
            "examples_null_like": text[null_like_mask].dropna().drop_duplicates().head(8).tolist(),
        })

    return {"columns": result}


def find_duplicates_tool(runtime: ToolRuntime, columns: list[str] | None = None):
    """
    Detect both exact duplicate rows and duplicate-key conflicts.

    When `columns` is empty, the tool reports complete duplicate rows.

    When key columns are supplied (for example Transaction_ID), the tool
    distinguishes two situations:

    1. exact duplicate groups:
       the key is repeated and all non-key values are identical -> safe candidate
       for automatic deduplication.

    2. conflict groups:
       the key is repeated but at least one non-key column differs -> unsafe to
       drop automatically; requires human review.
    """

    columns = columns or []

    # --------------------------------------------------------
    # COMPLETE ROW DUPLICATES
    # --------------------------------------------------------
    if not columns:
        duplicate_mask = runtime.df.duplicated(keep=False)
        involved = int(duplicate_mask.sum())
        removable = int(runtime.df.duplicated(keep="first").sum())

        examples = (
            runtime.df.loc[duplicate_mask]
            .head(8)
            .astype(str)
            .to_dict(orient="records")
        )

        return {
            "scope": "complete_rows",
            "duplicate_rows_involved": involved,
            "duplicate_rows_to_remove": removable,
            "safe_to_auto_remove": bool(removable > 0),
            "examples": examples,
        }

    # --------------------------------------------------------
    # DUPLICATE KEYS / IDENTIFIERS
    # --------------------------------------------------------
    for column in columns:
        _ensure_column(runtime.df, column)

    duplicate_mask = runtime.df.duplicated(
        subset=columns,
        keep=False,
    )

    duplicate_df = runtime.df.loc[duplicate_mask].copy()

    if duplicate_df.empty:
        return {
            "scope": "selected_columns",
            "columns": columns,
            "duplicate_rows_involved": 0,
            "duplicate_key_groups": 0,
            "exact_duplicate_groups": 0,
            "exact_duplicate_rows_to_remove": 0,
            "conflict_groups": 0,
            "conflict_rows": 0,
            "safe_to_drop_by_key": False,
            "exact_examples": [],
            "conflict_examples": [],
        }

    non_key_columns = [
        column
        for column in runtime.df.columns
        if column not in columns
    ]

    exact_duplicate_groups = 0
    exact_duplicate_rows_to_remove = 0
    conflict_groups = 0
    conflict_rows = 0
    exact_examples = []
    conflict_examples = []

    group_key = columns[0] if len(columns) == 1 else columns

    grouped = duplicate_df.groupby(
        group_key,
        dropna=False,
        sort=False,
    )

    total_groups = 0

    for key_value, group in grouped:
        if len(group) < 2:
            continue

        total_groups += 1

        if len(columns) == 1:
            key_values = {columns[0]: key_value}
        else:
            if not isinstance(key_value, tuple):
                key_value = (key_value,)
            key_values = {
                column: value
                for column, value in zip(columns, key_value)
            }

        # Compare all non-key columns. drop_duplicates treats rows with the same
        # values (including NA in the same positions) as identical for this purpose.
        distinct_payloads = (
            group[non_key_columns].drop_duplicates()
            if non_key_columns
            else pd.DataFrame(index=[0])
        )

        if len(distinct_payloads) <= 1:
            exact_duplicate_groups += 1
            exact_duplicate_rows_to_remove += len(group) - 1

            if len(exact_examples) < 6:
                exact_examples.append({
                    "key": _jsonable(key_values),
                    "rows_in_group": int(len(group)),
                    "sample_rows": _jsonable(
                        group.head(3).to_dict(orient="records")
                    ),
                })

        else:
            conflict_groups += 1
            conflict_rows += len(group)

            differing_columns = []
            for candidate in non_key_columns:
                if group[candidate].nunique(dropna=False) > 1:
                    differing_columns.append(str(candidate))

            if len(conflict_examples) < 8:
                conflict_examples.append({
                    "key": _jsonable(key_values),
                    "rows_in_group": int(len(group)),
                    "differing_columns": differing_columns,
                    "sample_rows": _jsonable(
                        group.head(4).to_dict(orient="records")
                    ),
                })

    return {
        "scope": "selected_columns",
        "columns": columns,
        "duplicate_rows_involved": int(duplicate_mask.sum()),
        "duplicate_key_groups": int(total_groups),
        "exact_duplicate_groups": int(exact_duplicate_groups),
        "exact_duplicate_rows_to_remove": int(exact_duplicate_rows_to_remove),
        "conflict_groups": int(conflict_groups),
        "conflict_rows": int(conflict_rows),
        "safe_to_drop_by_key": bool(
            total_groups > 0
            and conflict_groups == 0
            and exact_duplicate_rows_to_remove > 0
        ),
        "exact_examples": exact_examples,
        "conflict_examples": conflict_examples,
        "recommendation": (
            "Automatic key-based deduplication is safe only when conflict_groups == 0. "
            "If conflict_groups > 0, preserve the rows and require human review."
        ),
    }

def _extract_json_object(text: str):
    cleaned = (text or "").replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        start = cleaned.find("{")
        if start < 0:
            raise ValueError("La recherche externe n'a pas retourné de JSON exploitable.")
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(cleaned[start:])
            return data
        except Exception as exc:
            raise ValueError("La recherche externe n'a pas retourné de JSON exploitable.") from exc


def verify_external_reference_tool(
    runtime: ToolRuntime,
    column: str,
    values: list[str],
    reference_context: str,
):
    _ensure_column(runtime.df, column)

    actual_values = set(runtime.df[column].dropna().astype(str).tolist())
    requested = [str(v) for v in values if str(v) in actual_values][:30]
    if not requested:
        return {
            "column": column,
            "corrections": [],
            "message": "Aucune valeur demandée n'existe exactement dans la colonne.",
        }

    prompt = f"""
You are verifying values from a tabular dataset against external factual references.

Column: {column}
Context: {reference_context}
Values: {json.dumps(requested, ensure_ascii=False)}

Use web research when needed. Be conservative.
Return a correction ONLY when the original value is factually/standardly wrong or non-canonical AND the correct replacement is high-confidence.
Do not rewrite values merely for style. Do not guess.
If a value is already valid, return needs_change=false.

Return ONLY valid JSON with this shape:
{{
  "corrections": [
    {{
      "original_value": "exact original string",
      "corrected_value": "replacement or empty string",
      "needs_change": true,
      "confidence": "high|medium|low",
      "reason": "brief factual reason"
    }}
  ]
}}
""".strip()

    response = runtime.client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "browser_search"}],
        tool_choice="auto",
        temperature=0.1,
    )

    content = response.choices[0].message.content or ""
    data = _extract_json_object(content)

    corrections = []
    allowed = set(requested)
    for item in data.get("corrections", []):
        original = str(item.get("original_value", ""))
        corrected = str(item.get("corrected_value", ""))
        confidence = str(item.get("confidence", "")).lower()
        if (
            original in allowed
            and bool(item.get("needs_change", False))
            and confidence == "high"
            and corrected
            and corrected != original
        ):
            corrections.append({
                "old_value": original,
                "new_value": corrected,
                "reason": str(item.get("reason", "")),
            })

    return {
        "column": column,
        "reference_context": reference_context,
        "checked_count": len(requested),
        "corrections": corrections,
    }


def submit_cleaning_plan_tool(runtime: ToolRuntime, actions: list[dict]):
    # The cleaning engine performs the final allow-list validation.
    return {"actions": actions}


TOOL_FUNCTIONS = {
    "profile_dataset": profile_dataset_tool,
    "inspect_column": inspect_column_tool,
    "detect_numeric_issues": detect_numeric_issues_tool,
    "detect_date_issues": detect_date_issues_tool,
    "detect_text_anomalies": detect_text_anomalies_tool,
    "find_duplicates": find_duplicates_tool,
    "verify_external_reference": verify_external_reference_tool,
    "submit_cleaning_plan": submit_cleaning_plan_tool,
}


def execute_tool(runtime: ToolRuntime, name: str, arguments: dict):
    if name not in TOOL_FUNCTIONS:
        raise ValueError(f"Outil inconnu : {name}")
    result = TOOL_FUNCTIONS[name](runtime, **arguments)
    return _jsonable(result)
