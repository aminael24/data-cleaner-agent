from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from agent.groq_client import MODEL
from core.audit import NULL_LIKE, profile_dataset


@dataclass
class ToolRuntime:
    df: pd.DataFrame
    client: object


def _ensure_column(df: pd.DataFrame, column: str) -> None:
    if column not in df.columns:
        raise ValueError(f"Colonne inconnue : {column}")


def _jsonable(value: Any):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def profile_dataset_tool(runtime: ToolRuntime, **_) -> dict:
    return profile_dataset(runtime.df)


def inspect_column_tool(runtime: ToolRuntime, column: str) -> dict:
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
        "whitespace_count": int(
            (text.notna() & (text != text.str.strip())).fillna(False).sum()
        ),
        "top_values": {str(k): int(v) for k, v in top_values.items()},
        "sample_values": (
            non_null.astype(str)
            .drop_duplicates()
            .head(12)
            .tolist()
        ),
    }

    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        result.update(
            {
                "min": None if numeric.dropna().empty else float(numeric.min()),
                "max": None if numeric.dropna().empty else float(numeric.max()),
                "mean": None if numeric.dropna().empty else float(numeric.mean()),
                "negative_count": int((numeric < 0).fillna(False).sum()),
            }
        )

    return result


def _normalize_numeric_text(values: pd.Series) -> tuple[pd.Series, pd.Series, dict]:
    """Normalise des nombres texte sans modifier le DataFrame source."""
    raw = values.astype("string").str.strip()

    decimal_comma_mask = raw.str.match(r"^[-+]?\d+,\d+$", na=False)
    decimal_point_mask = raw.str.match(r"^[-+]?\d+\.\d+$", na=False)
    affix_mask = raw.str.contains(r"[^0-9,.+\-\s]", regex=True, na=False)

    cleaned = (
        raw
        .str.replace(r"[$€£¥]", "", regex=True)
        .str.replace(r"\b(?:USD|EUR|GBP|MAD|DHS?)\b", "", regex=True, case=False)
        .str.replace("\u00a0", "", regex=False)
        .str.replace(" ", "", regex=False)
    )

    # Ne garder que les chaînes réellement numériques après retrait devise.
    numeric_syntax = cleaned.str.match(r"^[-+]?(?:\d[\d.,]*|[.,]\d+)$", na=False)
    normalized = cleaned.where(numeric_syntax, pd.NA)

    both = normalized.str.contains(",", regex=False, na=False) & normalized.str.contains(
        ".", regex=False, na=False
    )
    euro_both = both & (normalized.str.rfind(",") > normalized.str.rfind("."))
    us_both = both & ~euro_both

    normalized.loc[euro_both] = (
        normalized.loc[euro_both]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    normalized.loc[us_both] = normalized.loc[us_both].str.replace(",", "", regex=False)

    only_comma = normalized.str.contains(",", regex=False, na=False) & ~normalized.str.contains(
        ".", regex=False, na=False
    )

    thousands_comma = normalized.str.match(r"^[-+]?\d{1,3}(?:,\d{3})+$", na=False)
    decimal_comma = only_comma & ~thousands_comma

    normalized.loc[thousands_comma] = normalized.loc[thousands_comma].str.replace(",", "", regex=False)
    normalized.loc[decimal_comma] = normalized.loc[decimal_comma].str.replace(",", ".", regex=False)

    converted = pd.to_numeric(normalized, errors="coerce")

    stats = {
        "decimal_comma_count": int(decimal_comma_mask.sum()),
        "decimal_point_count": int(decimal_point_mask.sum()),
        "currency_or_text_affix_count": int(affix_mask.sum()),
        "suggest_decimal_comma": bool(decimal_comma_mask.sum() > decimal_point_mask.sum()),
    }

    return raw, converted, stats


def detect_numeric_issues_tool(runtime: ToolRuntime, column: str) -> dict:
    _ensure_column(runtime.df, column)

    values = runtime.df[column].dropna().astype("string").str.strip()

    if values.empty:
        return {
            "column": column,
            "non_null_count": 0,
            "parseable_count": 0,
            "invalid_count": 0,
            "examples_invalid": [],
        }

    raw, converted, stats = _normalize_numeric_text(values)
    invalid_mask = converted.isna() & raw.ne("")

    result = {
        "column": column,
        "non_null_count": int(len(values)),
        "parseable_count": int(converted.notna().sum()),
        "invalid_count": int(invalid_mask.sum()),
        "examples_invalid": raw[invalid_mask].drop_duplicates().head(15).tolist(),
        "examples_values": raw.drop_duplicates().head(12).tolist(),
        "negative_count": int((converted < 0).fillna(False).sum()),
        **stats,
    }

    if converted.notna().any():
        result["min"] = float(converted.min())
        result["max"] = float(converted.max())

    return result


def detect_date_issues_tool(runtime: ToolRuntime, column: str) -> dict:
    _ensure_column(runtime.df, column)

    values = runtime.df[column].dropna().astype("string").str.strip()

    if values.empty:
        return {
            "column": column,
            "non_null_count": 0,
            "parseable_count": 0,
            "invalid_count": 0,
            "examples_invalid": [],
        }

    parsed_monthfirst = pd.to_datetime(
        values,
        errors="coerce",
        format="mixed",
        dayfirst=False,
    )
    parsed_dayfirst = pd.to_datetime(
        values,
        errors="coerce",
        format="mixed",
        dayfirst=True,
    )

    monthfirst_count = int(parsed_monthfirst.notna().sum())
    dayfirst_count = int(parsed_dayfirst.notna().sum())
    dayfirst = dayfirst_count > monthfirst_count

    parsed = parsed_dayfirst if dayfirst else parsed_monthfirst
    invalid_mask = parsed.isna()

    return {
        "column": column,
        "non_null_count": int(len(values)),
        "parseable_count": int(parsed.notna().sum()),
        "invalid_count": int(invalid_mask.sum()),
        "monthfirst_parseable": monthfirst_count,
        "dayfirst_parseable": dayfirst_count,
        "dayfirst_recommended": bool(dayfirst),
        "examples_invalid": values[invalid_mask].drop_duplicates().head(15).tolist(),
        "examples_values": values.drop_duplicates().head(12).tolist(),
    }


def detect_text_anomalies_tool(runtime: ToolRuntime, columns: list[str]) -> dict:
    result: list[dict] = []

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

        counts = normalized.dropna().value_counts()

        case_groups: dict[str, list[str]] = {}
        for value in counts.index[:500]:
            key = str(value).casefold()
            case_groups.setdefault(key, []).append(str(value))

        case_variants = [
            forms
            for forms in case_groups.values()
            if len(set(forms)) > 1
        ]

        # Typos probables seulement sur faible cardinalité pour éviter le bruit.
        probable_typos: dict[str, str] = {}
        unique_values = [str(v) for v in counts.index[:80]]
        if len(counts) <= 80:
            for value in unique_values:
                value_count = int(counts[value])
                source = value.casefold().strip()
                if len(source) < 3:
                    continue

                for other in unique_values:
                    if other == value:
                        continue
                    other_count = int(counts[other])
                    target = other.casefold().strip()

                    if other_count < max(3, 3 * value_count):
                        continue

                    if SequenceMatcher(None, source, target).ratio() >= 0.84:
                        probable_typos[value] = other
                        break

        result.append(
            {
                "column": column,
                "whitespace_count": int(whitespace_mask.sum()),
                "null_like_count": int(null_like_mask.sum()),
                "case_variant_groups": case_variants[:12],
                "probable_typos": probable_typos,
                "examples_whitespace": (
                    text[whitespace_mask]
                    .dropna()
                    .drop_duplicates()
                    .head(8)
                    .tolist()
                ),
                "examples_null_like": (
                    text[null_like_mask]
                    .dropna()
                    .drop_duplicates()
                    .head(8)
                    .tolist()
                ),
            }
        )

    return {"columns": result}


def find_duplicates_tool(
    runtime: ToolRuntime,
    columns: list[str] | None = None,
) -> dict:
    """
    Distingue :
    - doublons complets ;
    - clés répétées avec lignes identiques ;
    - clés répétées avec conflits sur d'autres colonnes.
    """
    columns = columns or []

    if not columns:
        duplicate_mask = runtime.df.duplicated(keep=False)
        involved = int(duplicate_mask.sum())
        removable = int(runtime.df.duplicated(keep="first").sum())

        return {
            "scope": "complete_rows",
            "duplicate_rows_involved": involved,
            "duplicate_rows_to_remove": removable,
            "safe_to_auto_remove": removable > 0,
            "examples": (
                runtime.df.loc[duplicate_mask]
                .head(6)
                .astype(str)
                .to_dict(orient="records")
            ),
        }

    for column in columns:
        _ensure_column(runtime.df, column)

    # On ignore les clés manquantes : deux NA ne prouvent pas un doublon d'identifiant.
    valid_key_mask = pd.Series(True, index=runtime.df.index)
    for column in columns:
        series = runtime.df[column]
        valid_key_mask &= series.notna() & series.astype("string").str.strip().ne("")

    valid_df = runtime.df.loc[valid_key_mask].copy()
    duplicate_mask = valid_df.duplicated(subset=columns, keep=False)
    duplicate_df = valid_df.loc[duplicate_mask].copy()

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

    non_key_columns = [c for c in runtime.df.columns if c not in columns]

    exact_duplicate_groups = 0
    exact_duplicate_rows_to_remove = 0
    conflict_groups = 0
    conflict_rows = 0
    exact_examples: list[dict] = []
    conflict_examples: list[dict] = []
    total_groups = 0

    group_key: str | list[str] = columns[0] if len(columns) == 1 else columns

    grouped = duplicate_df.groupby(group_key, dropna=False, sort=False)

    for key_value, group in grouped:
        if len(group) < 2:
            continue

        total_groups += 1

        if len(columns) == 1:
            key_values = {columns[0]: key_value}
        else:
            if not isinstance(key_value, tuple):
                key_value = (key_value,)
            key_values = dict(zip(columns, key_value))

        payload = (
            group[non_key_columns].drop_duplicates()
            if non_key_columns
            else pd.DataFrame(index=[0])
        )

        if len(payload) <= 1:
            exact_duplicate_groups += 1
            exact_duplicate_rows_to_remove += len(group) - 1

            if len(exact_examples) < 6:
                exact_examples.append(
                    {
                        "key": _jsonable(key_values),
                        "rows_in_group": int(len(group)),
                        "sample_rows": _jsonable(group.head(3).to_dict(orient="records")),
                    }
                )
        else:
            conflict_groups += 1
            conflict_rows += len(group)

            differing_columns = [
                str(candidate)
                for candidate in non_key_columns
                if group[candidate].nunique(dropna=False) > 1
            ]

            if len(conflict_examples) < 8:
                conflict_examples.append(
                    {
                        "key": _jsonable(key_values),
                        "rows_in_group": int(len(group)),
                        "differing_columns": differing_columns,
                        "sample_rows": _jsonable(group.head(4).to_dict(orient="records")),
                    }
                )

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
            "Use drop_duplicates_by_columns only when safe_to_drop_by_key=true. "
            "If conflict_groups>0, preserve rows and require human review."
        ),
    }


def _extract_json_object(text: str) -> dict:
    cleaned = (
        (text or "")
        .replace("```json", "")
        .replace("```JSON", "")
        .replace("```", "")
        .strip()
    )

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
            raise ValueError(
                "La recherche externe n'a pas retourné de JSON exploitable."
            ) from exc


def verify_external_reference_tool(
    runtime: ToolRuntime,
    column: str,
    values: list[str],
    reference_context: str,
) -> dict:
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
You are verifying categorical values from a tabular dataset against external factual references.

Column: {column}
Context: {reference_context}
Exact raw values: {json.dumps(requested, ensure_ascii=False)}

Be conservative.
Return a correction only when the raw value is clearly a non-canonical alias/code/translation/typo
and the replacement is high-confidence for the requested context.
Do not rewrite values merely for style. Do not guess.

Return ONLY valid JSON:
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
        temperature=0,
    )

    content = response.choices[0].message.content or ""
    data = _extract_json_object(content)

    corrections: list[dict] = []
    allowed = set(requested)

    for item in data.get("corrections", []) or []:
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
            corrections.append(
                {
                    "old_value": original,
                    "new_value": corrected,
                    "reason": str(item.get("reason", "")),
                }
            )

    return {
        "column": column,
        "reference_context": reference_context,
        "checked_count": len(requested),
        "corrections": corrections,
    }


def submit_cleaning_plan_tool(runtime: ToolRuntime, actions: list[dict]) -> dict:
    # Le Coverage Gate est dans graph.py.
    # Le moteur déterministe valide ensuite l'allow-list à l'exécution.
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


def execute_tool(runtime: ToolRuntime, name: str, arguments: dict) -> dict:
    if name not in TOOL_FUNCTIONS:
        raise ValueError(f"Outil inconnu : {name}")

    result = TOOL_FUNCTIONS[name](runtime, **arguments)
    return _jsonable(result)
