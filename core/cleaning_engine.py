import re

import pandas as pd


class CleaningPlanError(RuntimeError):
    pass


DEFAULT_NULL_TOKENS = [
    "", "na", "n/a", "null", "none", "nan", "unknown", "unk", "error", "err",
    "tbd", "-", "--", "?", "missing", "not available",
]


ALLOWED_OPERATIONS = {
    "normalize_column_names",
    "drop_empty_rows",
    "drop_empty_columns",
    "drop_duplicate_rows",
    "drop_duplicate_rows_after_cleaning",
    "drop_duplicates_by_columns",
    "replace_null_like",
    "strip_whitespace",
    "normalize_case",
    "replace_values",
    "to_numeric",
    "to_datetime",
    "set_negative_to_null",
    "fill_missing_from_formula",
    "recalculate_from_columns",
    "no_change",
}


def normalize_column_name(value):
    text = str(value)
    text = (
        text.replace("\ufeff", "")
        .replace("\r", " ")
        .replace("\n", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def resolve_column(df, requested, aliases):
    if not requested:
        raise CleaningPlanError("Une colonne est requise.")

    if requested in df.columns:
        return requested

    alias = aliases.get(requested)
    if alias and alias in df.columns:
        return alias

    wanted = normalize_column_name(requested)
    matches = [
        column for column in df.columns
        if normalize_column_name(column) == wanted
    ]
    if len(matches) == 1:
        return matches[0]

    raise CleaningPlanError(f"Colonne inconnue : {requested}")


def resolve_target_columns(df, action, aliases):
    requested = []
    column = str(action.get("column", "") or "").strip()
    if column:
        requested.append(column)

    for value in action.get("columns", []) or []:
        value = str(value).strip()
        if value and value not in requested:
            requested.append(value)

    if not requested:
        raise CleaningPlanError("Aucune colonne cible fournie.")

    return [resolve_column(df, value, aliases) for value in requested]


def _parse_numeric_value(value, decimal_comma=False):
    if pd.isna(value):
        return pd.NA

    text = str(value).strip()
    if not text:
        return pd.NA

    # Keep only numeric punctuation/sign; removes $, EUR, USD, spaces, etc.
    text = re.sub(r"[^0-9,.\-]", "", text)
    if not text:
        return pd.NA

    # Both separators present: last separator is treated as decimal separator.
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")  # 1.234,56
        else:
            text = text.replace(",", "")  # 1,234.56

    elif "," in text:
        if decimal_comma:
            # 112,05 -> 112.05 ; 8,4 -> 8.4
            if text.count(",") == 1:
                text = text.replace(",", ".")
            else:
                parts = text.split(",")
                if all(len(p) == 3 for p in parts[1:]):
                    text = "".join(parts)
                else:
                    text = "".join(parts[:-1]) + "." + parts[-1]
        else:
            # Auto: a single comma with <=3 trailing digits is likely decimal.
            if text.count(",") == 1:
                left, right = text.split(",", 1)
                text = f"{left}.{right}" if 1 <= len(right) <= 3 else left + right
            else:
                text = text.replace(",", "")

    elif "." in text:
        # IMPORTANT: keep $389.54 as 389.54 even when decimal_comma=True.
        if text.count(".") > 1:
            parts = text.split(".")
            if all(len(p) == 3 for p in parts[1:]):
                text = "".join(parts)
            else:
                text = "".join(parts[:-1]) + "." + parts[-1]
        elif decimal_comma:
            # In a European column, 1.234 can mean 1234; but 389.54 must remain decimal.
            left, right = text.split(".", 1)
            if len(right) == 3 and len(left.replace("-", "")) <= 3:
                text = left + right

    try:
        return float(text)
    except (TypeError, ValueError):
        return pd.NA


def _convert_numeric_series(series, decimal_comma=False):
    return series.apply(
        lambda value: _parse_numeric_value(value, decimal_comma=decimal_comma)
    ).astype("Float64")


def _as_numeric(series):
    """Série numérique (Float64) quel que soit l'état actuel de la colonne."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").astype("Float64")
    return _convert_numeric_series(series)


def _convert_datetime_series(series, dayfirst=False):
    try:
        return pd.to_datetime(
            series,
            errors="coerce",
            format="mixed",
            dayfirst=dayfirst,
        )
    except (TypeError, ValueError):
        return pd.to_datetime(series, errors="coerce", dayfirst=dayfirst)


def _count_changes(before, after):
    a = before.astype("string").fillna("<NA>")
    b = after.astype("string").fillna("<NA>")
    return int((a != b).sum())


def _bool_mask(mask):
    """Masque booléen sûr (les NA deviennent False)."""
    return mask.fillna(False).astype(bool)


def execute_cleaning_plan(original_df, plan):
    if not isinstance(plan, dict):
        raise CleaningPlanError("Plan de nettoyage invalide.")

    actions = plan.get("actions")
    if not isinstance(actions, list):
        raise CleaningPlanError("Le plan ne contient pas de liste d'actions.")

    df = original_df.copy(deep=True)
    aliases = {}
    execution_log = []

    for number, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            raise CleaningPlanError(f"Action #{number} invalide.")

        operation = str(action.get("operation", "") or "").strip()
        if operation not in ALLOWED_OPERATIONS:
            raise CleaningPlanError(f"Opération non autorisée : {operation}")

        reason = str(action.get("reason", "") or "")
        rows_before = len(df)
        affected_count = 0
        details = ""

        if operation == "normalize_column_names":
            old_columns = list(df.columns)
            new_columns = [normalize_column_name(column) for column in old_columns]
            if len(new_columns) != len(set(new_columns)):
                raise CleaningPlanError(
                    "La normalisation des colonnes créerait des noms en doublon."
                )
            affected_count = sum(old != new for old, new in zip(old_columns, new_columns))
            aliases.update({old: new for old, new in zip(old_columns, new_columns)})
            df.columns = new_columns
            details = f"{affected_count} nom(s) de colonne normalisé(s)."

        elif operation == "drop_empty_rows":
            before = len(df)
            df = df.dropna(axis=0, how="all").copy()
            affected_count = before - len(df)
            details = f"{affected_count} ligne(s) entièrement vide(s) supprimée(s)."

        elif operation == "drop_empty_columns":
            before_columns = list(df.columns)
            df = df.dropna(axis=1, how="all").copy()
            affected_count = len(before_columns) - len(df.columns)
            details = f"{affected_count} colonne(s) entièrement vide(s) supprimée(s)."

        elif operation == "drop_duplicate_rows":
            before = len(df)
            df = df.drop_duplicates().copy()
            affected_count = before - len(df)
            details = f"{affected_count} ligne(s) dupliquée(s) supprimée(s)."

        elif operation == "drop_duplicate_rows_after_cleaning":
            # Exécutée APRÈS strip / casse / remplacements : supprime les doublons
            # qui n'apparaissent qu'une fois les données normalisées.
            before = len(df)
            df = df.drop_duplicates().copy()
            affected_count = before - len(df)
            details = (
                f"{affected_count} doublon(s) révélé(s) par le nettoyage supprimé(s) "
                "(1re occurrence conservée)."
            )

        elif operation == "drop_duplicates_by_columns":
            targets = resolve_target_columns(df, action, aliases)
            before = len(df)
            df = df.drop_duplicates(subset=targets, keep="first").copy()
            affected_count = before - len(df)
            details = (
                f"{affected_count} doublon(s) supprimé(s) selon "
                + ", ".join(targets)
                + " (1re occurrence conservée)."
            )

        elif operation == "strip_whitespace":
            targets = resolve_target_columns(df, action, aliases)
            per_column = {}
            for column in targets:
                original = df[column].astype("string")
                cleaned = original.str.strip()
                mask = (original.notna() & (original != cleaned)).fillna(False)
                changed = int(mask.sum())
                if changed:
                    df[column] = cleaned
                per_column[column] = changed
                affected_count += changed

            if affected_count == 0:
                details = "Aucun espace superflu détecté. Aucune donnée modifiée."
            else:
                parts = [f"{col}: {count}" for col, count in per_column.items() if count]
                details = f"{affected_count} valeur(s) corrigée(s). " + ", ".join(parts) + "."

        elif operation == "replace_null_like":
            targets = resolve_target_columns(df, action, aliases)
            tokens = action.get("null_tokens", []) or DEFAULT_NULL_TOKENS
            normalized_tokens = {str(token).strip().casefold() for token in tokens}

            for column in targets:
                text = df[column].astype("string")
                normalized = text.str.strip().str.casefold()
                mask = (text.notna() & normalized.isin(normalized_tokens)).fillna(False)
                changed = int(mask.sum())
                df.loc[mask, column] = pd.NA
                affected_count += changed

            details = f"{affected_count} placeholder(s) converti(s) en valeur manquante."

        elif operation == "to_numeric":
            targets = resolve_target_columns(df, action, aliases)
            decimal_comma = bool(action.get("decimal_comma", False))
            results = []

            for column in targets:
                original = df[column].copy()
                converted = _convert_numeric_series(original, decimal_comma=decimal_comma)
                valid = int((original.notna() & converted.notna()).sum())
                invalid = int((original.notna() & converted.isna()).sum())
                changed = _count_changes(original, converted)
                df[column] = converted
                affected_count += changed
                results.append(f"{column}: {valid} convertie(s), {invalid} invalide(s)")

            details = "; ".join(results) + "."

        elif operation == "to_datetime":
            targets = resolve_target_columns(df, action, aliases)
            dayfirst = bool(action.get("dayfirst", False))
            results = []

            for column in targets:
                original = df[column].copy()
                converted = _convert_datetime_series(original, dayfirst=dayfirst)
                valid = int((original.notna() & converted.notna()).sum())
                invalid = int((original.notna() & converted.isna()).sum())
                changed = _count_changes(original, converted)
                df[column] = converted
                affected_count += changed
                results.append(f"{column}: {valid} date(s) valide(s), {invalid} invalide(s)")

            details = "; ".join(results) + "."

        elif operation == "replace_values":
            targets = resolve_target_columns(df, action, aliases)
            replacements = action.get("replacements", []) or []
            mapping = {}
            for item in replacements:
                if isinstance(item, dict) and "old_value" in item and "new_value" in item:
                    mapping[item["old_value"]] = item["new_value"]

            if not mapping:
                raise CleaningPlanError("Aucun remplacement valide n'a été fourni.")

            per_column = []
            for column in targets:
                original = df[column].copy()
                mask = original.isin(list(mapping.keys()))
                changed = int(mask.sum())
                df[column] = original.replace(mapping)
                affected_count += changed
                per_column.append(f"{column}: {changed}")

            details = (
                f"{affected_count} valeur(s) standardisée(s). "
                + ", ".join(per_column)
                + "."
            )

        elif operation == "normalize_case":
            targets = resolve_target_columns(df, action, aliases)
            mode = str(action.get("case_mode", "none")).lower()
            if mode not in {"lower", "upper", "title"}:
                raise CleaningPlanError(f"case_mode invalide : {mode}")

            for column in targets:
                original = df[column].astype("string")
                if mode == "lower":
                    cleaned = original.str.lower()
                elif mode == "upper":
                    cleaned = original.str.upper()
                else:
                    cleaned = original.str.title()
                changed = _count_changes(original, cleaned)
                if changed:
                    df[column] = cleaned
                affected_count += changed

            details = f"{affected_count} valeur(s) de texte normalisée(s)."

        elif operation == "set_negative_to_null":
            targets = resolve_target_columns(df, action, aliases)
            for column in targets:
                numeric = pd.to_numeric(df[column], errors="coerce")
                mask = (numeric < 0).fillna(False)
                changed = int(mask.sum())
                df.loc[mask, column] = pd.NA
                affected_count += changed
            details = f"{affected_count} valeur(s) négative(s) remplacée(s) par NA."

        elif operation == "fill_missing_from_formula":
            # columns = [facteur_1, facteur_2, produit] avec produit = facteur_1 × facteur_2.
            # Une case vide est remplie seulement si les DEUX autres valeurs de la ligne existent.
            cols = resolve_target_columns(df, action, aliases)
            if len(cols) != 3:
                raise CleaningPlanError(
                    "fill_missing_from_formula exige 3 colonnes : facteur 1, facteur 2, produit."
                )
            a_col, b_col, t_col = cols
            a = _as_numeric(df[a_col])
            b = _as_numeric(df[b_col])
            t = _as_numeric(df[t_col])

            def whole_only(series):
                known = series.dropna()
                return bool(len(known)) and bool((known % 1 == 0).all())

            # Les 3 masques sont calculés sur les valeurs d'origine : aucun remplissage en chaîne.
            fill_t = _bool_mask(t.isna() & a.notna() & b.notna())
            fill_a = _bool_mask(a.isna() & t.notna() & b.notna() & (b != 0))
            fill_b = _bool_mask(b.isna() & t.notna() & a.notna() & (a != 0))

            new_t = (a * b).round(2)
            new_a = t / b
            new_b = t / a

            # Une colonne d'entiers (ex. Quantity) n'accepte qu'un résultat entier.
            if whole_only(a):
                fill_a = fill_a & _bool_mask((new_a - new_a.round()).abs() < 1e-9)
                new_a = new_a.round()
            else:
                new_a = new_a.round(2)
            if whole_only(b):
                fill_b = fill_b & _bool_mask((new_b - new_b.round()).abs() < 1e-9)
                new_b = new_b.round()
            else:
                new_b = new_b.round(2)

            df[a_col] = a.where(~fill_a, new_a)
            df[b_col] = b.where(~fill_b, new_b)
            df[t_col] = t.where(~fill_t, new_t)

            n_a, n_b, n_t = int(fill_a.sum()), int(fill_b.sum()), int(fill_t.sum())
            affected_count = n_a + n_b + n_t
            details = (
                f"{affected_count} case(s) vide(s) remplie(s) : "
                f"{a_col}: {n_a}, {b_col}: {n_b}, {t_col}: {n_t}."
            )

        elif operation == "recalculate_from_columns":
            # cible = source_1 × source_2, uniquement sur les lignes où les 3 valeurs existent
            # et où l'écart dépasse la tolérance (2 %, même règle que le scan).
            target = resolve_column(df, str(action.get("column", "") or "").strip(), aliases)
            sources = [
                resolve_column(df, str(c).strip(), aliases)
                for c in (action.get("source_columns") or [])
            ]
            if len(sources) != 2:
                raise CleaningPlanError(
                    "recalculate_from_columns exige exactement 2 colonnes source."
                )

            left = _as_numeric(df[sources[0]])
            right = _as_numeric(df[sources[1]])
            actual = _as_numeric(df[target])

            expected = left * right
            tolerance = 0.02 * actual.abs().clip(lower=1)
            mask = _bool_mask(
                left.notna() & right.notna() & actual.notna()
                & ((expected - actual).abs() > tolerance)
            )

            affected_count = int(mask.sum())
            if affected_count:
                updated = actual.copy()
                updated[mask] = expected[mask].round(2)
                df[target] = updated

            details = (
                f"{affected_count} valeur(s) de {target} recalculée(s) "
                f"= {sources[0]} × {sources[1]}."
            )

        elif operation == "no_change":
            affected_count = 0
            details = "Aucune modification automatique. Validation humaine uniquement."

        execution_log.append({
            "number": number,
            "operation": operation,
            "column": action.get("column", "") or "",
            "columns": action.get("columns", []) or [],
            "reason": reason,
            "affected_count": int(affected_count),
            "details": details,
            "rows_before": int(rows_before),
            "rows_after": int(len(df)),
        })

    return df, execution_log
