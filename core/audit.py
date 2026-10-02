import re

import pandas as pd


NULL_LIKE = {
    "", "na", "n/a", "null", "none", "nan", "unknown", "unk",
    "tbd", "-", "--", "?", "missing", "not available",
}


def _safe_sample(series: pd.Series, limit: int = 8):
    values = (
        series.dropna()
        .astype(str)
        .map(str.strip)
    )
    values = values[values != ""].drop_duplicates()
    return values.head(limit).tolist()


def _numeric_candidate_ratio(series: pd.Series) -> float:
    if pd.api.types.is_numeric_dtype(series):
        return 1.0

    values = series.dropna().astype(str).str.strip()
    if values.empty:
        return 0.0

    cleaned = (
        values
        .str.replace(r"[^0-9,\.\-]", "", regex=True)
        .replace("", pd.NA)
    )
    converted = pd.to_numeric(
        cleaned.str.replace(",", ".", regex=False),
        errors="coerce",
    )
    return round(float(converted.notna().mean()), 4)


def _date_candidate_ratio(series: pd.Series) -> float:
    if pd.api.types.is_datetime64_any_dtype(series):
        return 1.0

    values = series.dropna().astype(str).str.strip()
    if values.empty:
        return 0.0

    sample = values.head(500)
    converted = pd.to_datetime(sample, errors="coerce", format="mixed")
    return round(float(converted.notna().mean()), 4)


def _whitespace_count(series: pd.Series) -> int:
    if not (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_string_dtype(series)
    ):
        return 0

    text = series.astype("string")
    mask = text.notna() & (text != text.str.strip())
    return int(mask.fillna(False).sum())


def _null_like_count(series: pd.Series) -> int:
    if not (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_string_dtype(series)
    ):
        return 0

    normalized = series.astype("string").str.strip().str.casefold()
    mask = normalized.isin(NULL_LIKE) & series.notna()
    return int(mask.fillna(False).sum())


def _normalize_column_key(value) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value).replace("\r", " ").replace("\n", " "),
    ).strip()


def profile_dataset(df: pd.DataFrame) -> dict:
    """Profile the full DataFrame locally and return only compact metadata."""
    columns = []

    for column in df.columns:
        series = df[column]
        item = {
            "name": str(column),
            "dtype": str(series.dtype),
            "missing_count": int(series.isna().sum()),
            "missing_pct": round(float(series.isna().mean() * 100), 2),
            "unique_count": int(series.nunique(dropna=True)),
            "sample_values": _safe_sample(series),
            "whitespace_count": _whitespace_count(series),
            "null_like_count": _null_like_count(series),
            "numeric_candidate_ratio": _numeric_candidate_ratio(series),
            "date_candidate_ratio": _date_candidate_ratio(series),
        }

        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce")
            item.update({
                "min": None if numeric.dropna().empty else float(numeric.min()),
                "max": None if numeric.dropna().empty else float(numeric.max()),
                "mean": None if numeric.dropna().empty else float(numeric.mean()),
                "negative_count": int((numeric < 0).fillna(False).sum()),
            })

        columns.append(item)

    header_issues = [
        {"original": str(c), "normalized": _normalize_column_key(c)}
        for c in df.columns
        if str(c) != _normalize_column_key(c)
    ]

    return {
        "rows": int(len(df)),
        "columns_count": int(df.shape[1]),
        "header_issues": header_issues,
        "total_missing": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated(keep=False).sum()),
        "duplicate_rows_to_remove": int(df.duplicated().sum()),
        "column_names": [str(c) for c in df.columns],
        "columns": columns,
    }


def validate_post_cleaning(
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
    execution_log: list[dict] | None = None,
) -> dict:
    """
    Validate the result after cleaning.

    This does not decide whether domain-specific values are correct.
    It detects structural regressions introduced by cleaning, such as:
    - unexpected row growth,
    - duplicate growth,
    - newly-created missing values,
    - unexpected column growth,
    - mismatch between reported and actual row removals.
    """

    execution_log = execution_log or []
    checks = []

    def add_check(name: str, status: str, message: str):
        checks.append({
            "name": name,
            "status": status,
            "message": message,
        })

    before_profile = profile_dataset(before_df)
    after_profile = profile_dataset(after_df)

    # --------------------------------------------------------
    # ROW COUNT
    # --------------------------------------------------------
    if len(after_df) > len(before_df):
        add_check(
            "Nombre de lignes",
            "error",
            f"Le nettoyage a augmenté le nombre de lignes : {len(before_df)} → {len(after_df)}.",
        )
    else:
        removed = len(before_df) - len(after_df)
        add_check(
            "Nombre de lignes",
            "ok",
            f"{removed} ligne(s) supprimée(s) ; aucune ligne ajoutée.",
        )

    expected_removed = sum(
        max(0, int(item.get("rows_before", 0)) - int(item.get("rows_after", 0)))
        for item in execution_log
    )
    actual_removed = len(before_df) - len(after_df)

    if expected_removed != actual_removed:
        add_check(
            "Traçabilité des suppressions",
            "warning",
            (
                f"Le journal indique {expected_removed} suppression(s), "
                f"mais la différence réelle est {actual_removed}."
            ),
        )
    else:
        add_check(
            "Traçabilité des suppressions",
            "ok",
            f"Les {actual_removed} suppression(s) de lignes correspondent au journal d'exécution.",
        )

    # --------------------------------------------------------
    # COLUMN COUNT
    # --------------------------------------------------------
    if after_df.shape[1] > before_df.shape[1]:
        add_check(
            "Nombre de colonnes",
            "error",
            f"Le nettoyage a créé des colonnes inattendues : {before_df.shape[1]} → {after_df.shape[1]}.",
        )
    else:
        add_check(
            "Nombre de colonnes",
            "ok",
            f"Structure contrôlée : {before_df.shape[1]} → {after_df.shape[1]} colonne(s).",
        )

    # --------------------------------------------------------
    # DUPLICATES
    # --------------------------------------------------------
    before_duplicates = before_profile["duplicate_rows_to_remove"]
    after_duplicates = after_profile["duplicate_rows_to_remove"]

    if after_duplicates > before_duplicates:
        add_check(
            "Doublons complets",
            "error",
            f"Le nombre de doublons complets a augmenté : {before_duplicates} → {after_duplicates}.",
        )
    elif after_duplicates == 0:
        add_check(
            "Doublons complets",
            "ok",
            "Aucun doublon complet restant.",
        )
    else:
        add_check(
            "Doublons complets",
            "warning",
            f"Il reste {after_duplicates} doublon(s) complet(s) supprimable(s).",
        )

    # --------------------------------------------------------
    # NEW MISSING VALUES
    # --------------------------------------------------------
    expected_missing_ops = {
        "to_numeric",
        "to_datetime",
        "replace_null_like",
        "set_negative_to_null",
    }

    expected_missing_targets = set()
    for item in execution_log:
        if item.get("operation") not in expected_missing_ops:
            continue

        column = str(item.get("column", "") or "").strip()
        if column:
            expected_missing_targets.add(_normalize_column_key(column))

        for column_name in item.get("columns", []) or []:
            expected_missing_targets.add(_normalize_column_key(column_name))

    before_map = {_normalize_column_key(c): c for c in before_df.columns}
    after_map = {_normalize_column_key(c): c for c in after_df.columns}
    common_keys = sorted(set(before_map) & set(after_map))
    common_index = before_df.index.intersection(after_df.index)

    new_missing = []

    for key in common_keys:
        before_col = before_map[key]
        after_col = after_map[key]

        before_series = before_df.loc[common_index, before_col]
        after_series = after_df.loc[common_index, after_col]

        created_mask = before_series.notna() & after_series.isna()
        created_count = int(created_mask.sum())

        if created_count > 0:
            new_missing.append({
                "column": str(after_col),
                "count": created_count,
                "expected": key in expected_missing_targets,
            })

    unexpected_missing = [item for item in new_missing if not item["expected"]]
    expected_missing = [item for item in new_missing if item["expected"]]

    if unexpected_missing:
        details = ", ".join(
            f"{item['column']}: +{item['count']}"
            for item in unexpected_missing
        )
        add_check(
            "Valeurs manquantes nouvelles",
            "error",
            f"Des valeurs manquantes inattendues ont été créées : {details}.",
        )
    elif expected_missing:
        details = ", ".join(
            f"{item['column']}: +{item['count']}"
            for item in expected_missing
        )
        add_check(
            "Valeurs manquantes nouvelles",
            "warning",
            (
                "Des valeurs manquantes ont été créées par des opérations qui peuvent le faire "
                f"(conversion/nullification) : {details}. Vérifiez-les avant export."
            ),
        )
    else:
        add_check(
            "Valeurs manquantes nouvelles",
            "ok",
            "Aucune nouvelle valeur manquante créée sur les lignes conservées.",
        )

    # --------------------------------------------------------
    # TYPE CHANGES
    # --------------------------------------------------------
    type_changes = []
    for key in common_keys:
        before_col = before_map[key]
        after_col = after_map[key]
        before_type = str(before_df[before_col].dtype)
        after_type = str(after_df[after_col].dtype)
        if before_type != after_type:
            type_changes.append({
                "column": str(after_col),
                "before": before_type,
                "after": after_type,
            })

    if type_changes:
        details = "; ".join(
            f"{item['column']}: {item['before']} → {item['after']}"
            for item in type_changes[:10]
        )
        add_check(
            "Types de données",
            "ok",
            f"Conversions de type détectées : {details}.",
        )
    else:
        add_check(
            "Types de données",
            "ok",
            "Aucun changement de type de données.",
        )

    statuses = {item["status"] for item in checks}
    if "error" in statuses:
        overall_status = "error"
    elif "warning" in statuses:
        overall_status = "warning"
    else:
        overall_status = "ok"

    return {
        "status": overall_status,
        "checks": checks,
        "before": before_profile,
        "after": after_profile,
        "new_missing": new_missing,
        "type_changes": type_changes,
    }
