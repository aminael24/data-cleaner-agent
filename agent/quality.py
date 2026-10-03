"""
Rapport de performance du nettoyage : le MÊME scan est appliqué avant et après.

Chaque catégorie compte des lignes/cellules en anomalie. Le taux de résolution compare le
nombre d'anomalies avant et après. Les catégories "à revoir" (valeurs négatives, clés répétées
en conflit, incohérences entre colonnes) sont affichées mais exclues du taux : elles ne se
corrigent pas automatiquement sans risque.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from agent.preaudit import NULL_RE, _norm_key, scan_dataset

PHONE_NAME_RE = re.compile(r"phone|mobile|(?:^|_)tel(?:_|$)", re.IGNORECASE)

# (clé, libellé, à revoir manuellement ?)
CATEGORIES = [
    ("whitespace", "Espaces superflus", False),
    ("null_like", "Marqueurs nuls déguisés (unknown, N/A…)", False),
    ("number_format", "Nombres mal formatés ($, milliers, virgule)", False),
    ("unparseable", "Valeurs non numériques en colonne numérique", False),
    ("date_formats", "Dates à formats multiples", False),
    ("invalid_dates", "Dates impossibles", False),
    ("variants", "Variantes de catégories (casse, ponctuation, fautes)", False),
    ("emails", "E-mails mal formés ou en majuscules", False),
    ("names", "Noms mal casés", False),
    ("negatives", "Valeurs négatives (à revoir)", True),
    ("ages", "Âges hors bornes selon le type (à revoir)", True),
    ("id_formats", "Formats d'identifiant / téléphone", False),
    ("duplicates", "Doublons complets", False),
    ("key_conflicts", "Clés répétées (à revoir)", True),
    ("relations", "Incohérences entre colonnes (à revoir)", True),
]


def _variant_rows(info: dict) -> int:
    """Lignes écrites dans une forme minoritaire (casse/ponctuation) ou fautive (typo)."""
    values = info.get("values") or {}
    if not values:
        return 0
    groups: dict[str, list[str]] = {}
    for form in values:
        groups.setdefault(_norm_key(form), []).append(form)
    typo_keys = {_norm_key(source) for source in (info.get("probable_typos") or {})}

    rows = 0
    for key, forms in groups.items():
        total = sum(values[f] for f in forms)
        if key in typo_keys:
            rows += total
        elif len(forms) > 1:
            rows += total - max(values[f] for f in forms)
    return rows


def _identifier_format_rows(series: pd.Series, name: str) -> int:
    """Lignes dont le format diffère de la forme dominante (masque) ou dont la longueur est aberrante."""
    values = series.dropna().astype(str).str.strip()
    values = values[~(values.str.fullmatch(NULL_RE) | values.eq(""))]
    if values.empty:
        return 0

    masks = values.map(lambda v: re.sub(r"[A-Za-z]+", "A", re.sub(r"\d+", "9", v)))
    bad = masks != masks.value_counts().index[0]

    if PHONE_NAME_RE.search(name):
        digits = values.map(lambda v: len(re.sub(r"\D", "", v)))
        bad = bad | (digits != digits.value_counts().index[0])

    return int(bad.sum())


def issue_counts(df: pd.DataFrame, findings: dict) -> dict[str, int]:
    counts = {key: 0 for key, _, _ in CATEGORIES}

    for name, info in (findings.get("columns") or {}).items():
        counts["whitespace"] += int(info.get("whitespace", 0))
        counts["null_like"] += sum((info.get("null_like") or {}).values())
        counts["number_format"] += sum(int(info.get(k, 0)) for k in ("currency", "thousands_sep", "decimal_comma"))

        if not info.get("identifier_like"):
            counts["unparseable"] += sum((info.get("unparseable") or {}).values())

        formats = info.get("date_formats") or {}
        if len(formats) > 1:
            counts["date_formats"] += sum(formats.values()) - max(formats.values())
        counts["invalid_dates"] += sum((info.get("invalid_dates") or {}).values())

        counts["variants"] += _variant_rows(info)

        counts["emails"] += int(info.get("uppercase", 0)) + int((info.get("invalid_format") or {}).get("count", 0))
        counts["names"] += int((info.get("name_case_inconsistent") or {}).get("count", 0))
        # Les âges négatifs sont déjà comptés dans la catégorie dédiée.
        if not info.get("age_policy"):
            counts["negatives"] += int(info.get("negative", 0))
        counts["ages"] += int(info.get("implausible_age", 0))

        if info.get("identifier_like") and name in df.columns:
            counts["id_formats"] += _identifier_format_rows(df[name], name)

    counts["duplicates"] = int(findings.get("full_duplicate_rows_to_remove", 0) or 0)
    counts["key_conflicts"] = sum(
        int(v.get("duplicate_rows_involved", 0)) for v in (findings.get("identifier_duplicates") or {}).values()
    )
    counts["relations"] = sum(int(r.get("mismatch_rows", 0)) for r in findings.get("relationships") or [])
    return counts


def _distinct_forms(findings: dict) -> int:
    return sum(
        int(info.get("distinct_forms", 0))
        for info in (findings.get("columns") or {}).values()
        if info.get("kind") == "categorical"
    )


def build_quality_report(before_df: pd.DataFrame, after_df: pd.DataFrame) -> dict[str, Any]:
    before_findings = scan_dataset(before_df)
    after_findings = scan_dataset(after_df)

    before = issue_counts(before_df, before_findings)
    after = issue_counts(after_df, after_findings)

    rows = []
    for key, label, manual in CATEGORIES:
        if before[key] == 0 and after[key] == 0:
            continue
        rows.append({"key": key, "label": label, "before": before[key], "after": after[key], "manual": manual})

    auto = [r for r in rows if not r["manual"]]
    before_total = sum(r["before"] for r in auto)
    after_total = sum(r["after"] for r in auto)
    resolved = max(before_total - after_total, 0)

    return {
        "rows": rows,
        "before_total": before_total,
        "after_total": after_total,
        "resolved_pct": round(100 * resolved / before_total, 1) if before_total else 100.0,
        "manual_after": sum(r["after"] for r in rows if r["manual"]),
        "distinct_forms_before": _distinct_forms(before_findings),
        "distinct_forms_after": _distinct_forms(after_findings),
        "rows_before": int(len(before_df)),
        "rows_after": int(len(after_df)),
    }
