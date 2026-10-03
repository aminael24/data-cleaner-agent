"""
Plan de base DÉTERMINISTE + fusion avec les décisions sémantiques du LLM.

Pourquoi
--------
Avec une limite de 8 000 tokens/minute, on ne peut pas renvoyer tout l'audit au LLM à
chaque tour. Et ce n'est pas nécessaire : 90 % du nettoyage est mécanique
(espaces, marqueurs nuls, casse, fautes de frappe évidentes, nombres en texte, dates...).

Ici Python construit un plan de base sûr qui COUVRE toutes les anomalies du scan.
Le LLM ne garde que ce que Python ne sait pas faire : la connaissance du monde
(CA = Canada, Italie = Italy, M = Male...). Ses actions sont fusionnées au plan de base.

Si le LLM est indisponible (quota Groq, JSON invalide...), le plan de base suffit :
l'utilisateur obtient quand même un plan complet.

Règles de sécurité
------------------
- Les doublons supprimés automatiquement sont UNIQUEMENT les lignes strictement identiques dans
  le fichier brut (drop_duplicate_rows s'exécute AVANT tout nettoyage).
- Tout ce qui est risqué (négatifs, doublons révélés par le nettoyage, clés en conflit,
  incohérences entre colonnes, dates impossibles, remplissage par calcul) devient une VRAIE
  action, mais DÉCOCHÉE par défaut (requires_review=True) : l'humain coche s'il veut l'appliquer.
- Le LLM ne peut jamais proposer ces actions (voir _clean_llm_action).
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from agent.preaudit import (
    DATE_RE,
    EMAIL_RE,
    NON_NEGATIVE_NAME_RE,
    NULL_RE,
    _norm_key,
    _parse_number,
    age_policy_for_column,
    check_coverage,
)
from agent.tools import ToolRuntime, find_duplicates_tool


# ============================================================
# CONSTANTES
# ============================================================

# Le moteur exécute les actions dans l'ordre du plan.
# drop_duplicate_rows EN PREMIER : on ne compare que les lignes brutes strictement identiques.
# replace_values AVANT normalize_case : les old_value sont les formes brutes (strip seulement).
# fill_missing_from_formula / recalculate_from_columns APRÈS to_numeric / set_negative_to_null.
# drop_duplicate_rows_after_cleaning APRÈS tout le nettoyage (doublons révélés par strip/casse).
OPERATION_ORDER = [
    "normalize_column_names",
    "drop_duplicate_rows",
    "strip_whitespace",
    "replace_null_like",
    "replace_values",
    "normalize_case",
    "to_numeric",
    "to_datetime",
    "set_negative_to_null",
    "fill_missing_from_formula",
    "recalculate_from_columns",
    "drop_empty_rows",
    "drop_empty_columns",
    "drop_duplicate_rows_after_cleaning",
    "drop_duplicates_by_columns",
    "no_change",
]

ALLOWED_OPERATIONS = set(OPERATION_ORDER)

# Opérations que le LLM n'a PAS le droit de proposer (destructives ou décidées par Python).
LLM_FORBIDDEN_OPERATIONS = {
    "set_negative_to_null",
    "drop_duplicate_rows",
    "drop_duplicates_by_columns",
    "drop_duplicate_rows_after_cleaning",
    "recalculate_from_columns",
    "fill_missing_from_formula",
}

NUMBER_WORDS = {
    # EN
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100,
    # FR
    "zéro": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sept": 7,
    "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16, "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "cent": 100,
}

MAX_FORMS_PER_COLUMN = 40
MAX_OPEN_COLUMNS = 6


# ============================================================
# FABRIQUE D'ACTIONS
# ============================================================

def _act(operation: str, reason: str, *, column=None, columns=None, confidence="high", review=False, **extra) -> dict:
    action: dict[str, Any] = {
        "operation": operation,
        "reason": str(reason),
        "confidence": confidence,
        "requires_review": bool(review),
    }
    if column:
        action["column"] = column
    if columns:
        action["columns"] = list(columns)
    for key, value in extra.items():
        if value is not None:
            action[key] = value
    return action


def _pairs(mapping: dict[str, str]) -> list[dict[str, str]]:
    return [{"old_value": old, "new_value": new} for old, new in mapping.items() if old != new]


# ============================================================
# CATÉGORIEL : casse / ponctuation / fautes de frappe
# ============================================================

def _category_maps(values: dict[str, int], typos: dict[str, str]) -> dict[str, Any]:
    groups: dict[str, list[str]] = {}
    for form in values:
        groups.setdefault(_norm_key(form), []).append(form)

    dominant = {key: max(forms, key=lambda f: values[f]) for key, forms in groups.items()}
    group_total = {key: sum(values[f] for f in forms) for key, forms in groups.items()}

    # ---- fautes de frappe : tout le groupe "fautif" -> forme dominante du groupe cible ----
    typo_map: dict[str, str] = {}
    typo_auto = True
    typo_keys: set[str] = set()
    for source, canonical in typos.items():
        k_src, k_dst = _norm_key(source), _norm_key(canonical)
        if k_src not in groups or k_dst not in groups or k_src == k_dst:
            continue
        if re.sub(r"\D", "", k_src) != re.sub(r"\D", "", k_dst):
            continue  # chiffres différents : tranche/montant/code différent, pas une faute de frappe
        ratio = SequenceMatcher(None, k_src, k_dst).ratio()
        freq = group_total[k_dst] / max(group_total[k_src], 1)
        if not (ratio >= 0.85 and freq >= 10):
            typo_auto = False  # moins évident -> revue humaine
        typo_keys.add(k_src)
        for form in groups[k_src]:
            typo_map[form] = dominant[k_dst]

    # ---- casse / ponctuation : toutes les formes d'un groupe -> forme dominante ----
    harmonize: dict[str, str] = {}
    harmonize_auto = True
    for key, forms in groups.items():
        if key in typo_keys or len(forms) < 2:
            continue
        if values[dominant[key]] / max(group_total[key], 1) < 0.6:
            harmonize_auto = False  # pas de forme clairement majoritaire
        for form in forms:
            if form != dominant[key]:
                harmonize[form] = dominant[key]

    final_counts: dict[str, int] = {}
    for form, count in values.items():
        target = typo_map.get(form) or harmonize.get(form) or form
        final_counts[target] = final_counts.get(target, 0) + count

    return {
        "typos": typo_map,
        "typos_auto": typo_auto,
        "harmonize": harmonize,
        "harmonize_auto": harmonize_auto,
        "final_counts": final_counts,
    }


# ============================================================
# E-MAILS : réparation prudente du '@' manquant
# ============================================================

def _email_repairs(series: pd.Series) -> dict[str, str]:
    values = series.dropna().astype(str).str.strip()
    valid = values[values.str.fullmatch(EMAIL_RE, na=False)]
    if valid.empty:
        return {}

    domains = valid.str.rsplit("@", n=1).str[-1].str.lower().value_counts()
    known = sorted((d for d, c in domains.items() if c >= 5), key=len, reverse=True)

    repairs: dict[str, str] = {}
    for raw in values[~values.str.contains("@", regex=False)].unique():
        lowered = raw.lower()
        for domain in known:
            if lowered.endswith(domain) and len(raw) > len(domain):
                local = raw[: -len(domain)]
                if re.fullmatch(r"[A-Za-z0-9._%+\-]+", local):
                    repairs[raw] = f"{local}@{raw[-len(domain):]}"
                break
    return repairs


# ============================================================
# NOMBRES / IDENTIFIANTS
# ============================================================

def _decimal_comma_dominant(series: pd.Series) -> bool:
    text = series.dropna().astype(str).str.strip()
    comma = int(text.str.contains(r"\d,\d{1,2}(?!\d)", regex=True).sum())
    point = int(text.str.contains(r"\d\.\d{1,2}(?!\d)", regex=True).sum())
    return comma > point


def _id_prefix_repairs(series: pd.Series) -> dict[str, str]:
    """'CUST-1581' -> '1581' quand la grande majorité des identifiants sont de purs chiffres."""
    values = series.dropna().astype(str).str.strip()
    if values.empty or values.str.fullmatch(r"\d+").mean() < 0.8:
        return {}
    prefixed = values[values.str.fullmatch(r"[A-Za-z]+[-_ ]?\d+")]
    return {raw: re.sub(r"^[A-Za-z]+[-_ ]?", "", raw) for raw in prefixed.unique()}


PHONE_NAME_RE = re.compile(r"phone|mobile|(?:^|_)tel(?:_|$)", re.IGNORECASE)


# ============================================================
# DOUBLONS : exacts (supprimés d'office) vs cachés par le formatage (opt-in)
# ============================================================

def _normalized_duplicate_count(df: pd.DataFrame) -> int:
    """Lignes dupliquées seulement après strip + casse (invisibles dans le fichier brut)."""
    normalized = df.astype("string").apply(lambda col: col.str.strip().str.casefold())
    return int(normalized.duplicated(keep="first").sum())


# ============================================================
# DATES : normalisation déterministe vers AAAA-MM-JJ
# ============================================================

def _date_mask(value: str) -> str:
    return re.sub(r"\d", "9", value)


def _date_plan(series: pd.Series) -> dict[str, Any]:
    """
    Convertit chaque date non-ISO en AAAA-MM-JJ AVANT to_datetime.

    Raison : un `dayfirst=True` global inverse jour/mois des dates ISO (2025-02-01 -> 2025-01-02).
    La convention jj/mm ou mm/jj est déduite PAR FORMAT (ex. 99/99/9999 vs 99-99-9999) à partir des
    dates sans ambiguïté (un nombre > 12 prouve quel champ est le jour).
    """
    vals = series.dropna().astype(str).str.strip()
    vals = vals[vals.str.fullmatch(DATE_RE)]
    iso = vals.str.fullmatch(r"\d{4}-\d{2}-\d{2}")
    masks = vals.map(_date_mask)

    certain: dict[str, str] = {}
    inferred: dict[str, str] = {}
    unresolved: dict[str, str] = {}

    for mask in sorted(set(masks[~iso])):
        rows = vals[masks == mask]
        parts = rows.str.extract(r"^(\d+)\D(\d+)\D(\d+)$").astype(int)

        if mask.startswith("9999"):  # AAAA/MM/JJ : aucune ambiguïté
            for raw, (y, m, d) in zip(rows.drop_duplicates(), parts.loc[rows.drop_duplicates().index].values):
                certain[raw] = f"{y:04d}-{m:02d}-{d:02d}"
            continue
        if not mask.endswith("9999"):  # année sur 2 chiffres : on ne devine pas
            continue

        day_certain = int((parts[0] > 12).sum())
        month_certain = int((parts[1] > 12).sum())
        one_sided = (day_certain > 0) != (month_certain > 0)
        dayfirst = day_certain >= month_certain

        unique_rows = rows.drop_duplicates()
        for raw, (a, b, y) in zip(unique_rows, parts.loc[unique_rows.index].values):
            if a > 12 and b > 12:
                continue  # impossible : restera invalide
            if a > 12:
                day, month, bucket = a, b, certain
            elif b > 12:
                month, day, bucket = a, b, certain
            else:
                day, month = (a, b) if dayfirst else (b, a)
                bucket = inferred if one_sided else unresolved
            bucket[raw] = f"{y:04d}-{month:02d}-{day:02d}"

    final = vals.map(lambda v: certain.get(v) or inferred.get(v) or unresolved.get(v) or v)
    invalid = int(pd.to_datetime(final, errors="coerce", format="%Y-%m-%d").isna().sum())

    return {"certain": certain, "inferred": inferred, "unresolved": unresolved, "invalid": invalid}


# ============================================================
# TÉLÉPHONES : une seule forme, chiffres uniquement
# ============================================================

def _phone_plan(series: pd.Series) -> tuple[dict[str, str], list[str]]:
    """Retire séparateurs, 0 initial et indicatif pour retomber sur la forme dominante du fichier."""
    vals = series.dropna().astype(str).str.strip()
    vals = vals[~(vals.str.fullmatch(NULL_RE) | vals.eq(""))]
    phones = vals[vals.str.fullmatch(r"\+?[\d\s().\-]+")]
    digits = phones.map(lambda v: re.sub(r"\D", "", v))

    junk = sorted(set(phones[digits.str.len() < 6]))
    good = phones[digits.str.len() >= 6]
    if good.empty:
        return {}, junk

    lengths = digits[good.index].str.len().value_counts()
    dominant = int(lengths.index[0])
    reliable = lengths.iloc[0] / len(good) >= 0.5

    mapping: dict[str, str] = {}
    for raw in good.drop_duplicates():
        international = raw.startswith("+") or raw.startswith("00")
        number = re.sub(r"\D", "", raw)
        if international and number.startswith("00"):
            number = number[2:]

        normalized = None
        if reliable:
            for country_len in (0, 1, 2, 3):
                if country_len and not international:
                    break
                rest = number[country_len:]
                if rest.startswith("0") and len(rest) - 1 == dominant:
                    rest = rest[1:]
                if len(rest) == dominant:
                    normalized = rest
                    break
        if normalized is None:
            normalized = ("+" if international else "") + number
        if normalized != raw:
            mapping[raw] = normalized

    return mapping, junk


def _implausible_tokens(series: pd.Series, low: float = 0, high: float | None = 120) -> list[str]:
    tokens = []
    for raw in series.dropna().astype(str).str.strip().drop_duplicates():
        number, _ = _parse_number(raw)
        if number is not None and (number < low or (high is not None and number > high)):
            tokens.append(raw)
    return tokens


# ============================================================
# RELATIONS ENTRE COLONNES : combien de vides se calculent ?
# ============================================================

def _fillable_counts(df: pd.DataFrame, left: list[str], target: str) -> dict[str, int]:
    """
    Combien de cases vides se calculent à partir des deux autres colonnes (cible = left0 × left1).
    Les valeurs 'ERROR' / 'UNKNOWN' etc. sont comptées comme vides, car elles seront
    vidées par replace_null_like avant le remplissage.
    """
    def num(col: str) -> pd.Series:
        def parse(value):
            if pd.isna(value):
                return None
            return _parse_number(str(value).strip())[0]

        return pd.to_numeric(df[col].map(parse), errors="coerce")

    a, b, t = num(left[0]), num(left[1]), num(target)
    return {
        target: int((t.isna() & a.notna() & b.notna()).sum()),
        left[0]: int((a.isna() & t.notna() & b.notna() & (b != 0)).sum()),
        left[1]: int((b.isna() & t.notna() & a.notna() & (a != 0)).sum()),
    }


# ============================================================
# PLAN DE BASE
# ============================================================

def build_baseline(df: pd.DataFrame, findings: dict) -> dict[str, Any]:
    columns: dict[str, dict] = findings.get("columns") or {}
    actions: list[dict] = []
    trace: list[dict] = []
    open_forms: dict[str, dict[str, int]] = {}

    # 1) espaces ---------------------------------------------------------------
    ws_cols = [c for c, i in columns.items() if i.get("whitespace")]
    if ws_cols:
        actions.append(_act("strip_whitespace", f"Espaces en début/fin ({len(ws_cols)} colonnes)", columns=ws_cols))

    # 2) marqueurs nuls (groupés par jeu de tokens identique) --------------------
    null_groups: dict[tuple, list[str]] = {}
    for c, i in columns.items():
        if i.get("null_like"):
            null_groups.setdefault(tuple(sorted(i["null_like"])), []).append(c)
    for tokens, cols in null_groups.items():
        actions.append(_act("replace_null_like", f"Marqueurs nuls : {', '.join(tokens)}", columns=cols, null_tokens=list(tokens)))

    # 3) catégoriel ---------------------------------------------------------------
    for c, i in columns.items():
        if i.get("kind") != "categorical" or not i.get("values"):
            continue
        maps = _category_maps(i["values"], i.get("probable_typos") or {})
        if maps["harmonize"]:
            actions.append(_act(
                "replace_values", f"Harmoniser casse/ponctuation ({len(maps['harmonize'])} formes)",
                column=c, replacements=_pairs(maps["harmonize"]),
                confidence="high" if maps["harmonize_auto"] else "medium", review=not maps["harmonize_auto"],
            ))
        if maps["typos"]:
            actions.append(_act(
                "replace_values", f"Fautes de frappe probables ({len(maps['typos'])} formes)",
                column=c, replacements=_pairs(maps["typos"]),
                confidence="high" if maps["typos_auto"] else "medium", review=not maps["typos_auto"],
            ))
        if 2 <= len(maps["final_counts"]) <= MAX_FORMS_PER_COLUMN:
            open_forms[c] = dict(sorted(maps["final_counts"].items(), key=lambda kv: -kv[1]))

    # 4) e-mails ---------------------------------------------------------------------
    for c, i in columns.items():
        if i.get("kind") != "email":
            continue
        if i.get("invalid_format"):
            repairs = _email_repairs(df[c])
            invalid_count = i["invalid_format"]["count"]
            if repairs:
                remaining = max(invalid_count - len(repairs), 0)
                suffix = f" · {remaining} autres restent invalides" if remaining else ""
                actions.append(_act(
                    "replace_values", f"Insérer le '@' manquant ({len(repairs)} e-mails){suffix}",
                    column=c, replacements=_pairs(repairs), confidence="medium", review=True,
                ))
            else:
                actions.append(_act(
                    "no_change", f"{invalid_count} e-mails invalides : à corriger à la main",
                    column=c, confidence="medium", review=True,
                ))
        if i.get("uppercase"):
            actions.append(_act("normalize_case", f"{i['uppercase']} e-mails en majuscules", column=c, case_mode="lower"))

    # 5) noms de personnes -----------------------------------------------------------
    for c, i in columns.items():
        if i.get("kind") == "text" and i.get("name_case_inconsistent"):
            actions.append(_act(
                "normalize_case", f"{i['name_case_inconsistent']['count']} noms tout en majuscules/minuscules",
                column=c, case_mode="title", confidence="medium", review=True,
            ))

    # 6) numériques ------------------------------------------------------------------
    to_numeric_groups: dict[bool, list[str]] = {}
    negative_flags: list[str] = []  # colonnes avec négatifs : action OPT-IN (décochée)
    for c, i in columns.items():
        if i.get("kind") != "numeric" or i.get("identifier_like"):
            continue

        unparseable: dict[str, int] = i.get("unparseable") or {}
        words = {t: str(NUMBER_WORDS[t.strip().casefold()]) for t in unparseable if t.strip().casefold() in NUMBER_WORDS}
        junk = [t for t in unparseable if t not in words]

        if words:
            actions.append(_act(
                "replace_values", f"Nombres écrits en lettres : {', '.join(words)}",
                column=c, replacements=_pairs(words), confidence="high",
            ))
        if junk:
            actions.append(_act(
                "replace_null_like", f"Valeurs non numériques → vides : {', '.join(junk)[:45]}",
                column=c, null_tokens=junk, confidence="medium",
            ))

        text_column = not pd.api.types.is_numeric_dtype(df[c])
        if text_column:
            to_numeric_groups.setdefault(_decimal_comma_dominant(df[c]), []).append(c)

        if i.get("implausible_age"):
            policy = i.get("age_policy") or age_policy_for_column(c) or {"kind": "unknown", "minimum": 0, "maximum": None}
            tokens = _implausible_tokens(df[c], low=policy["minimum"], high=policy["maximum"])
            kind = policy["kind"]
            if kind == "company":
                description = "âges d’entreprise négatifs (<0)"
            elif kind == "human":
                description = "âges humains hors bornes (<0 ou >120, règle de plausibilité)"
            else:
                description = "âges négatifs (<0, type de colonne non déterminé)"
            if tokens:
                actions.append(_act(
                    "replace_null_like",
                    f"{i['implausible_age']} {description} : cochez pour les remplacer par des valeurs manquantes",
                    column=c, null_tokens=tokens, confidence="medium", review=True,
                ))
            else:
                actions.append(_act(
                    "no_change", f"{i['implausible_age']} {description} : valeurs à vérifier",
                    column=c, confidence="medium", review=True,
                ))
        elif i.get("negative"):
            negative_flags.append(c)

    for decimal_comma, cols in to_numeric_groups.items():
        actions.append(_act(
            "to_numeric", f"Convertir en nombres ({len(cols)} colonnes)",
            columns=cols, decimal_comma=decimal_comma,
        ))

    # Négatifs : VRAIE action set_negative_to_null, mais DÉCOCHÉE (review=True).
    # Un négatif peut être un retour, un remboursement, une annulation ou une correction
    # comptable : l'humain décide colonne par colonne. Sans clic, les valeurs sont conservées.
    for c in negative_flags:
        count = columns[c]["negative"]
        strictly_positive = bool(NON_NEGATIVE_NAME_RE.search(c))  # salary, price, stock...
        actions.append(_act(
            "set_negative_to_null",
            f"{count} négatives : cochez pour les vider (sinon conservées : retours ?)",
            column=c,
            confidence="medium" if strictly_positive else "low",
            review=True,
        ))

    # 7) dates : normalisation ISO déterministe, puis to_datetime SANS dayfirst ----------
    for c, i in columns.items():
        if i.get("kind") != "date":
            continue
        plan = _date_plan(df[c])
        resolved = {**plan["certain"], **plan["inferred"]}
        if resolved:
            actions.append(_act(
                "replace_values",
                f"Dates → AAAA-MM-JJ ({len(resolved)} formats ; jj/mm ou mm/jj déduit par format)",
                column=c, replacements=_pairs(resolved),
                confidence="medium" if plan["inferred"] else "high",
            ))
        if plan["unresolved"]:
            actions.append(_act(
                "replace_values", f"Dates jj/mm vs mm/jj ambiguës ({len(plan['unresolved'])}) : convention incertaine",
                column=c, replacements=_pairs(plan["unresolved"]), confidence="low", review=True,
            ))

        # Des dates impossibles (31/02, mois 13) deviendraient vides : décision humaine.
        has_invalid = bool(i.get("invalid_dates")) or plan["invalid"] > 0
        if has_invalid:
            n_bad = plan["invalid"] or sum((i.get("invalid_dates") or {}).values())
            actions.append(_act(
                "to_datetime",
                f"Convertir en dates · {n_bad} dates impossibles deviendront vides (à valider)",
                column=c, dayfirst=False, confidence="medium", review=True,
            ))
        else:
            actions.append(_act("to_datetime", "Convertir en dates (AAAA-MM-JJ)", column=c, dayfirst=False))

    # 8) identifiants / téléphones ------------------------------------------------------
    for c, i in columns.items():
        if not i.get("identifier_like"):
            continue

        prefix = _id_prefix_repairs(df[c]) if i.get("key_candidate") else {}
        if prefix:
            actions.append(_act(
                "replace_values", f"Retirer le préfixe texte des identifiants ({len(prefix)})",
                column=c, replacements=_pairs(prefix), confidence="medium", review=True,
            ))

        if PHONE_NAME_RE.search(c):
            phone_map, phone_junk = _phone_plan(df[c])
            if phone_junk:
                actions.append(_act(
                    "replace_null_like", f"Numéros invalides (<6 chiffres) → vides : {', '.join(phone_junk)[:30]}",
                    column=c, null_tokens=phone_junk, confidence="high",
                ))
            if phone_map:
                actions.append(_act(
                    "replace_values", f"Téléphones : chiffres seuls, même longueur ({len(phone_map)} formats)",
                    column=c, replacements=_pairs(phone_map), confidence="medium", review=True,
                ))
            elif i.get("format_patterns"):
                actions.append(_act(
                    "no_change", "Formats de téléphone hétérogènes : à valider",
                    column=c, confidence="medium", review=True,
                ))
        elif i.get("format_patterns") and not prefix:
            actions.append(_act(
                "no_change", "Formats d'identifiant hétérogènes : à valider",
                column=c, confidence="medium", review=True,
            ))

    # 9) clés répétées : find_duplicates exécuté LOCALEMENT ----------------------------
    runtime = ToolRuntime(df=df, client=None)
    for c in (findings.get("identifier_duplicates") or {}):
        result = find_duplicates_tool(runtime, [c])
        trace.append({
            "tool": "find_duplicates", "arguments": {"columns": [c]},
            "result_summary": json.dumps(
                {k: result.get(k) for k in ("duplicate_key_groups", "exact_duplicate_groups", "conflict_groups", "safe_to_drop_by_key")},
                ensure_ascii=False,
            ),
            "memory_summary": "", "status": "ok",
        })
        if result.get("safe_to_drop_by_key"):
            actions.append(_act(
                "drop_duplicates_by_columns", f"Clé {c} répétée, lignes identiques : dédoublonner",
                columns=[c], confidence="medium", review=True,
            ))
        else:
            # Conflits : on propose quand même l'action, décochée, avec avertissement clair.
            conflicts = int(result.get("conflict_groups", 0) or 0)
            actions.append(_act(
                "drop_duplicates_by_columns",
                f"{c} répété ({conflicts} conflits) : cochez pour ne garder que la 1re ligne",
                columns=[c], confidence="low", review=True,
            ))

    # 10) doublons complets / relations -----------------------------------------------
    # Doublons EXACTS du fichier brut : supprimés d'office (l'action s'exécute en premier).
    exact = int(findings.get("full_duplicate_rows_to_remove", 0) or 0)
    if exact > 0:
        actions.append(_act(
            "drop_duplicate_rows",
            f"{exact} lignes strictement identiques (comparées avant nettoyage)",
        ))

    # Doublons révélés seulement par le nettoyage (espaces, casse) : action OPT-IN,
    # exécutée APRÈS le nettoyage, donc sur les données réellement normalisées.
    hidden = _normalized_duplicate_count(df) - exact
    if hidden > 0:
        actions.append(_act(
            "drop_duplicate_rows_after_cleaning",
            f"~{hidden} doublons probables (espaces/casse) : cochez pour les supprimer",
            confidence="medium", review=True,
        ))

    # Relations entre colonnes : remplissage des vides par calcul (opt-in)
    # + recalcul des valeurs fausses (opt-in).
    for relation in findings.get("relationships") or []:
        left = [str(x) for x in relation.get("left_columns") or []]
        target = str(relation["target_column"])
        mismatch = int(relation.get("mismatch_rows", 0) or 0)

        if len(left) == 2:
            fillable = _fillable_counts(df, left, target)
            total_fill = sum(fillable.values())
            if total_fill > 0:
                actions.append(_act(
                    "fill_missing_from_formula",
                    f"~{total_fill} vides remplis par calcul : {target} = {left[0]} × {left[1]}",
                    columns=[left[0], left[1], target], confidence="medium", review=True,
                ))

        if mismatch <= 0:
            continue
        if len(left) == 2:
            actions.append(_act(
                "recalculate_from_columns",
                f"{mismatch} lignes violent {relation['formula']} : cochez pour recalculer {target}",
                column=target, source_columns=left, confidence="medium", review=True,
            ))
        else:
            actions.append(_act(
                "no_change", f"{mismatch} lignes violent {relation['formula']}",
                column=target, confidence="medium", review=True,
            ))

    # ---- résumé pour l'UI -------------------------------------------------------------
    trace.insert(0, {
        "tool": "baseline_plan", "arguments": {},
        "result_summary": f"{len(actions)} actions déterministes construites localement (sans LLM)",
        "memory_summary": "", "status": "ok",
    })

    # ---- décisions ouvertes pour le LLM (petit message) -----------------------------
    open_columns = dict(list(open_forms.items())[:MAX_OPEN_COLUMNS])
    return {"actions": _sorted(_merge_replace_actions(actions)), "trace": trace, "open_decisions": open_columns}


# ============================================================
# RÉSUMÉ COMPACT DU PLAN DE BASE POUR LE LLM
# ============================================================

def summarize_actions(actions: list[dict], limit: int = 30) -> list[str]:
    lines = []
    for action in actions[:limit]:
        targets = action.get("column") or ",".join(action.get("columns") or []) or "*"
        extra = f" ({len(action['replacements'])} pairs)" if action.get("replacements") else ""
        review = " [review]" if action.get("requires_review") else ""
        lines.append(f"{action['operation']}: {targets}{extra}{review}")
    return lines


# ============================================================
# FUSION + COUVERTURE
# ============================================================

def _lowest_confidence(a: str, b: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return a if order.get(a, 1) <= order.get(b, 1) else b


def _merge_replace_actions(actions: list[dict]) -> list[dict]:
    """
    Fusionne les replace_values d'une MÊME colonne (et de même niveau de revue) en une seule carte.
    Les actions à revoir et les automatiques restent séparées pour garder des cases à cocher distinctes.
    Les replace_null_like ne sont PAS fusionnés : leurs jetons sont propres à chaque colonne.
    """
    merged: list[dict] = []
    index: dict[tuple, int] = {}

    for action in actions:
        column = action.get("column")
        if action.get("operation") == "replace_values" and column:
            key = (column, bool(action.get("requires_review")))
            if key in index:
                target = merged[index[key]]
                pairs = {r["old_value"]: r["new_value"] for r in target["replacements"]}
                pairs.update({r["old_value"]: r["new_value"] for r in action.get("replacements") or []})
                target["replacements"] = _pairs(pairs)
                target["confidence"] = _lowest_confidence(target["confidence"], action.get("confidence", "medium"))
                target["reason"] = f"Standardiser les valeurs ({len(pairs)} corrections)"
                continue
            action = {**action, "replacements": list(action.get("replacements") or [])}
            index[key] = len(merged)
        merged.append(action)
    return merged


def _sorted(actions: list[dict]) -> list[dict]:
    rank = {operation: index for index, operation in enumerate(OPERATION_ORDER)}
    return sorted(actions, key=lambda a: rank.get(a.get("operation"), len(rank)))


def _clean_llm_action(raw: Any, identifier_columns: set[str]) -> dict | None:
    # Le rôle du LLM est limité aux correspondances sémantiques.
    # Il ne peut pas contourner les cases à cocher du plan déterministe.
    if not isinstance(raw, dict) or raw.get("operation") != "replace_values":
        return None

    action = dict(raw)
    action["reason"] = str(action.get("reason") or "Décision sémantique du LLM")
    action["confidence"] = action.get("confidence") if action.get("confidence") in ("high", "medium", "low") else "medium"
    review = action.get("requires_review", True)
    action["requires_review"] = review if isinstance(review, bool) else True

    # Garde-fou : le LLM ne décide jamais d'effacer des valeurs, de supprimer des lignes,
    # de recalculer ni de remplir une colonne. Tout cela est géré par Python (actions décochées).
    if action["operation"] in LLM_FORBIDDEN_OPERATIONS:
        return None

    # Garde-fou : jamais de conversion numérique sur un identifiant / téléphone.
    targets = {str(action.get("column"))} | {str(c) for c in action.get("columns") or []}
    if action["operation"] == "to_numeric" and targets & identifier_columns:
        return None

    if action["operation"] == "replace_values":
        reps = [
            {"old_value": str(r["old_value"]), "new_value": str(r["new_value"])}
            for r in action.get("replacements") or []
            if isinstance(r, dict) and "old_value" in r and "new_value" in r
            and r["old_value"] is not None and r["new_value"] is not None
            and str(r["new_value"]).strip()
            and not NULL_RE.fullmatch(str(r["new_value"]).strip())
        ]
        if not reps:
            return None
        action["replacements"] = reps

    return action


def _resolve_replacement_chains(actions: list[dict]) -> list[dict]:
    """Résout les chaînes automatiques sans incorporer une décision à cocher.

    Une proposition CA -> Canada à revoir ne doit jamais transformer une
    correction automatique ca -> CA en ca -> Canada.
    """
    per_column: dict[str, dict[str, str]] = {}
    for action in actions:
        if (action.get("operation") == "replace_values" and action.get("column")
                and not action.get("requires_review")):
            mapping = per_column.setdefault(action["column"], {})
            for r in action.get("replacements") or []:
                mapping[r["old_value"]] = r["new_value"]

    def resolve(mapping: dict[str, str], value: str) -> str:
        seen: set[str] = set()
        while value in mapping and value not in seen and mapping[value] != value:
            seen.add(value)
            value = mapping[value]
        return value

    result = []
    for action in actions:
        if (action.get("operation") == "replace_values" and action.get("column")
                and not action.get("requires_review")):
            mapping = per_column[action["column"]]
            reps = {}
            for r in action.get("replacements") or []:
                final = resolve(mapping, r["new_value"])
                if final != r["old_value"]:
                    reps[r["old_value"]] = final
            if not reps:
                continue
            action = {**action, "replacements": _pairs(reps)}
        result.append(action)
    return result


def finalize_plan(baseline_actions: list[dict], llm_actions: list[dict], requirements: list[dict], identifier_columns: list[str] | None = None) -> tuple[list[dict], dict]:
    id_cols = set(identifier_columns or [])
    accepted = [a for a in (_clean_llm_action(r, id_cols) for r in llm_actions or []) if a]

    merged = _resolve_replacement_chains(list(baseline_actions) + accepted)

    unique, seen = [], set()
    for action in merged:
        key = json.dumps(action, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            unique.append(action)
    final = _sorted(_merge_replace_actions(unique))

    # Filet de sécurité : toute exigence encore non couverte devient une revue humaine explicite.
    missing = check_coverage(final, requirements)
    for item in missing:
        flag = _act(
            "no_change", str(item["issue"]),
            column=None if item["column"] == "(whole dataset)" else item["column"],
            confidence="low", review=True,
        )
        final.append(flag)

    return final, {
        "llm_actions_received": len(llm_actions or []),
        "llm_actions_kept": len(accepted),
        "auto_flagged": len(missing),
    }
