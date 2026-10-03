from __future__ import annotations

import re
import math
import unicodedata
from difflib import SequenceMatcher
from itertools import permutations
from typing import Any

import pandas as pd

NULL_RE = re.compile(
    r"^(?:unknown|unk|error|err|n/?a|#n/?a|null|none|nan|nil|missing|undefined|"
    r"-+|\?+|\.+|not[_ ]?(?:a[_ ]?)?(?:date|number|available|applicable)|"
    r"[a-z]+_unknown|unknown_[a-z]+)$",
    re.IGNORECASE,
)
CURRENCY_RE = re.compile(r"[$€£¥]|\b(?:USD|EUR|GBP|MAD|DHS?)\b", re.IGNORECASE)
DATE_RE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
KEY_NAME_RE = re.compile(r"(?:^|_)(?:id|uuid|ref|sku|key)(?:_|$)", re.IGNORECASE)
FORMAT_IDENTIFIER_RE = re.compile(r"phone|mobile|(?:^|_)tel(?:_|$)|zip|postal|iban|siret", re.IGNORECASE)
COUNTRY_NAME_RE = re.compile(r"country|pays|nation", re.IGNORECASE)
AGE_NAME_RE = re.compile(r"(?:^|_)age(?:_|$)", re.IGNORECASE)
NON_NEGATIVE_NAME_RE = re.compile(
    r"price|prix|salary|salaire|wage|weight|poids|height|stock|(?:^|_)cost(?:_|$)|cout",
    re.IGNORECASE,
)
NAME_NAME_RE = re.compile(r"(?:^|_)(?:full_?name|name|nom|prenom|first_?name|last_?name)(?:_|$)", re.IGNORECASE)
EMAIL_NAME_RE = re.compile(r"mail|email|e_mail", re.IGNORECASE)
MAX_CATEGORICAL_VALUES = 80
MAX_EXAMPLES = 10


def age_policy_for_column(name: str, age_type: str | None = None) -> dict[str, Any] | None:
    """Interprète le sujet d'une colonne d'âge avant de choisir ses bornes.

    Une colonne ambiguë ne reçoit aucune borne supérieure arbitraire.
    age_type permet une déclaration explicite ('human', 'company', 'unknown').
    Les bornes restent des règles de revue, pas des suppressions automatiques.
    """
    text = re.sub(r"([a-zà-ÿ])([A-Z])", r"\1_\2", str(name))
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    words = set(re.findall(r"[a-z0-9]+", text))
    if age_type is None and not words.intersection({"age", "ages"}):
        return None
    if age_type is not None and age_type not in {"human", "company", "unknown"}:
        raise ValueError("Le type d'âge doit être human, company ou unknown.")
    company_words = {
        "company", "companies", "business", "firm", "enterprise", "entreprise",
        "entreprises", "societe", "societes", "organization", "organisation", "startup",
    }
    human_words = {
        "human", "humain", "person", "personne", "employee", "employe", "employes",
        "customer", "client", "patient", "student", "etudiant", "candidate", "candidat",
        "user", "utilisateur", "child", "enfant", "individual", "individu",
    }
    if age_type is None:
        company = bool(words & company_words)
        human = bool(words & human_words)
        age_type = "company" if company and not human else "human" if human and not company else "unknown"
    return {"kind": age_type, "minimum": 0, "maximum": 120 if age_type == "human" else None}


def _mask(value: str) -> str:
    return re.sub(r"[A-Za-zÀ-ÿ]+", "A", re.sub(r"\d", "9", value))


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _parse_number(raw: str) -> tuple[float | None, set[str]]:
    original = str(raw)
    text = CURRENCY_RE.sub("", original).strip()
    flags: set[str] = set()
    if text != original.strip():
        flags.add("currency")
    text = text.replace("\u00a0", "").replace(" ", "")
    if not re.fullmatch(r"[-+]?(?:\d[\d.,]*|[.,]\d+)", text):
        return None, flags
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
            flags.add("decimal_comma")
        else:
            text = text.replace(",", "")
            flags.add("thousands_sep")
    elif "," in text:
        if re.fullmatch(r"[-+]?\d{1,3}(?:,\d{3})+", text):
            text = text.replace(",", "")
            flags.add("thousands_sep")
        else:
            text = text.replace(",", ".")
            flags.add("decimal_comma")
    elif text.count(".") > 1:
        if re.fullmatch(r"[-+]?\d{1,3}(?:\.\d{3})+", text):
            text = text.replace(".", "")
            flags.add("thousands_sep")
        else:
            return None, flags
    try:
        return float(text), flags
    except ValueError:
        return None, flags


def _top(counter: pd.Series, limit: int = MAX_EXAMPLES) -> dict[str, int]:
    return {str(k): int(v) for k, v in counter.head(limit).items()}


def _safe_examples(values: pd.Series, limit: int = MAX_EXAMPLES) -> list[str]:
    return values.dropna().astype(str).drop_duplicates().head(limit).tolist()


def _is_probable_date_series(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    return float(values.str.fullmatch(DATE_RE).mean())


def _scan_column(name: str, series: pd.Series, n_rows: int, age_type: str | None = None):
    out: dict[str, Any] = {}
    age_policy = age_policy_for_column(name, age_type)
    if age_policy:
        out["age_policy"] = age_policy
    missing = int(series.isna().sum())
    if missing:
        out["missing"] = missing
    non_null = series.dropna().astype(str)
    if non_null.empty:
        out["kind"] = "empty"
        return out, None
    stripped = non_null.str.strip()
    whitespace = int((non_null != stripped).sum())
    if whitespace:
        out["whitespace"] = whitespace
        out["whitespace_examples"] = _safe_examples(non_null[non_null != stripped], 5)
    null_mask = stripped.str.fullmatch(NULL_RE, na=False) | stripped.eq("")
    null_like = stripped[null_mask]
    if len(null_like):
        out["null_like"] = _top(null_like.value_counts(), 10)
    vals = stripped[~null_mask]
    if vals.empty:
        out["kind"] = "empty"
        return out, None
    key_named = bool(KEY_NAME_RE.search(name))
    format_identifier = bool(FORMAT_IDENTIFIER_RE.search(name))
    identifier_like = key_named or format_identifier
    if identifier_like:
        out["identifier_like"] = True
    unique_ratio = float(vals.nunique(dropna=True) / max(len(vals), 1))
    if key_named and unique_ratio >= 0.70:
        out["key_candidate"] = True
        out["unique_ratio"] = round(unique_ratio, 4)
    masks = vals.map(_mask).value_counts()
    if len(masks) > 1 and float(masks.iloc[1:].sum() / len(vals)) >= 0.02:
        examples: dict[str, dict[str, Any]] = {}
        for mask in masks.head(8).index:
            mask_values = vals[vals.map(_mask) == mask]
            examples[str(mask)] = {"count": int(masks[mask]), "example": str(mask_values.iloc[0])}
        out["format_patterns"] = examples
    parsed_cache: dict[str, tuple[float | None, set[str]]] = {}
    flag_counts = {"currency": 0, "thousands_sep": 0, "decimal_comma": 0}
    unparseable: list[str] = []
    parsed_values: list[float] = []
    for raw in vals:
        raw_s = str(raw)
        if raw_s not in parsed_cache:
            parsed_cache[raw_s] = _parse_number(raw_s)
        number, flags = parsed_cache[raw_s]
        if number is None:
            unparseable.append(raw_s)
        else:
            parsed_values.append(number)
            for flag in flags:
                if flag in flag_counts:
                    flag_counts[flag] += 1
    numeric_share = len(parsed_values) / max(len(vals), 1)
    date_share = _is_probable_date_series(vals)
    email_share = float(vals.str.contains("@", regex=False).mean())
    if EMAIL_NAME_RE.search(name) or email_share >= 0.5:
        out["kind"] = "email"
        uppercase = int((vals != vals.str.lower()).sum())
        invalid_mask = ~vals.str.fullmatch(EMAIL_RE, na=False)
        if uppercase:
            out["uppercase"] = uppercase
        if bool(invalid_mask.any()):
            out["invalid_format"] = {"count": int(invalid_mask.sum()), "examples": _safe_examples(vals[invalid_mask], 8)}
        return out, None
    if date_share >= 0.5:
        out["kind"] = "date"
        date_vals = vals[vals.str.fullmatch(DATE_RE, na=False)]
        out["date_formats"] = _top(date_vals.map(lambda v: re.sub(r"\d", "9", str(v))).value_counts(), 8)
        first_gt12 = second_gt12 = ambiguous = 0
        for value in date_vals:
            parts = re.split(r"[-/.]", str(value))
            if len(parts) != 3 or len(parts[0]) == 4:
                continue
            try:
                first = int(parts[0]); second = int(parts[1])
            except ValueError:
                continue
            if first > 12:
                first_gt12 += 1
            elif second > 12:
                second_gt12 += 1
            else:
                ambiguous += 1
        out["dayfirst_evidence"] = {"day_first_certain": first_gt12, "month_first_certain": second_gt12, "ambiguous_dd_mm_or_mm_dd": ambiguous}

        def parses_as_date(value: str) -> bool:
            for dayfirst in (False, True):
                parsed = pd.to_datetime(value, errors="coerce", format="mixed", dayfirst=dayfirst)
                if not pd.isna(parsed):
                    return True
            return False

        invalid_mask = vals.map(lambda v: not (bool(DATE_RE.fullmatch(str(v))) and parses_as_date(str(v))))
        invalid_values = vals[invalid_mask]
        if len(invalid_values):
            out["invalid_dates"] = _top(invalid_values.value_counts(), 10)
        return out, None
    if numeric_share >= 0.5:
        out["kind"] = "numeric"
        out["numeric_share"] = round(numeric_share, 4)
        if parsed_values:
            numbers = pd.Series(parsed_values, dtype="float64")
            if not identifier_like:
                out["min"] = round(float(numbers.min()), 4)
                out["max"] = round(float(numbers.max()), 4)
                negatives = int((numbers < 0).sum())
                if negatives:
                    out["negative"] = negatives
                if age_policy:
                    upper = age_policy["maximum"]
                    invalid = numbers < age_policy["minimum"]
                    if upper is not None:
                        invalid = invalid | (numbers > upper)
                    implausible = int(invalid.sum())
                    if implausible:
                        out["implausible_age"] = implausible
                        # Toutes les valeurs concernées, sans limite d'exemples.
                        out["implausible_age_tokens"] = [
                            raw for raw, (number, _) in parsed_cache.items()
                            if number is not None and (
                                number < age_policy["minimum"]
                                or (upper is not None and number > upper)
                            )
                        ]
        for flag, count in flag_counts.items():
            if count:
                out[flag] = count
        if unparseable:
            out["unparseable"] = _top(pd.Series(unparseable, dtype="string").value_counts(), 12)
        numeric_series = None
        if not identifier_like:
            mapped = stripped.map(lambda raw: parsed_cache.get(str(raw), (None, set()))[0])
            numeric_series = pd.to_numeric(mapped, errors="coerce").reindex(series.index)
        return out, numeric_series
    counts = vals.value_counts()
    if len(counts) <= MAX_CATEGORICAL_VALUES and not identifier_like:
        out["kind"] = "categorical"
        out["values"] = {str(k): int(v) for k, v in counts.items()}
        groups: dict[str, list[str]] = {}
        for value in counts.index:
            groups.setdefault(_norm_key(str(value)), []).append(str(value))
        case_variants: list[list[str]] = []
        punctuation_variants: list[list[str]] = []
        for forms in groups.values():
            if len(forms) <= 1:
                continue
            casefolded = {form.casefold() for form in forms}
            if len(casefolded) == 1:
                case_variants.append(forms)
            else:
                punctuation_variants.append(forms)
        if case_variants:
            out["case_variants"] = case_variants[:12]
        if punctuation_variants:
            out["punctuation_variants"] = punctuation_variants[:12]
        key_counts = {key: int(sum(int(counts[form]) for form in forms)) for key, forms in groups.items()}
        probable_typos: dict[str, str] = {}
        normalized_keys = list(groups.keys())
        for key in normalized_keys:
            count = key_counts[key]
            if not key:
                continue
            for other in normalized_keys:
                if other == key or not other:
                    continue
                other_count = key_counts[other]
                if other_count < max(3, 3 * count):
                    continue
                # Chiffres différents = valeurs différentes (tranches, montants, codes),
                # pas une faute de frappe.
                if re.sub(r"\D", "", key) != re.sub(r"\D", "", other):
                    continue
                ratio = SequenceMatcher(None, key, other).ratio()
                if ratio >= 0.82:
                    source = max(groups[key], key=lambda form: int(counts[form]))
                    canonical = max(groups[other], key=lambda form: int(counts[form]))
                    probable_typos[source] = canonical
                    break
        if probable_typos:
            out["probable_typos"] = probable_typos
        out["distinct_forms"] = int(len(counts))
        out["distinct_normalized"] = int(len(groups))
        if COUNTRY_NAME_RE.search(name):
            short_codes = [str(v) for v in counts.index if re.fullmatch(r"[A-Za-z]{2,3}", str(v).strip())]
            long_names = [str(v) for v in counts.index if re.search(r"[A-Za-zÀ-ÿ]{4,}", str(v).strip())]
            out["country_reference_candidate"] = True
            out["country_values"] = [str(v) for v in counts.index[:40]]
            if short_codes and long_names:
                out["mixed_country_codes_and_names"] = True
                out["country_code_examples"] = short_codes[:12]
        return out, None
    out["kind"] = "identifier" if identifier_like else "text"
    if NAME_NAME_RE.search(name) and not identifier_like:
        letters = vals[vals.str.contains(r"[A-Za-zÀ-ÿ]", regex=True, na=False)]
        suspicious_case = letters[(letters.str.islower() | letters.str.isupper()) & (letters != letters.str.title())]
        if len(suspicious_case):
            out["name_case_inconsistent"] = {"count": int(len(suspicious_case)), "examples": _safe_examples(suspicious_case, 8)}
    return out, None


def _is_binary_indicator(series: pd.Series) -> bool:
    """Un indicateur 0/1 ne constitue pas une mesure à multiplier."""
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    return not numeric.empty and set(numeric.unique()).issubset({0, 1})


def _find_relationships(numeric_columns):
    """Propose des hypothèses statistiques, toujours soumises à revue humaine.

    Les zéros communs ne sont pas des preuves d'une formule. Les indicateurs
    binaires et les colonnes constantes sont exclus, même comme facteurs.
    """
    found = []
    candidates = {}
    for name, series in numeric_columns.items():
        numeric = pd.to_numeric(series, errors="coerce")
        numeric = numeric.where(numeric.map(lambda v: pd.notna(v) and math.isfinite(v)))
        if _is_binary_indicator(numeric) or numeric.dropna().nunique() < 2:
            continue
        candidates[name] = numeric
    names = list(candidates)
    for a, b, c in permutations(names, 3):
        if a > b:
            continue
        frame = pd.concat([candidates[a], candidates[b], candidates[c]], axis=1).dropna()
        if len(frame) < 100:
            continue
        expected = frame.iloc[:, 0] * frame.iloc[:, 1]
        actual = frame.iloc[:, 2]
        if not expected.map(math.isfinite).all():
            continue
        informative = (expected.abs() > 1e-9) | (actual.abs() > 1e-9)
        informative_count = int(informative.sum())
        if informative_count < max(50, math.ceil(len(frame) * 0.15)):
            continue
        # Éviter les facteurs constants sur les seules lignes informatives.
        if any(frame.loc[informative].iloc[:, i].nunique() < 2 for i in range(3)):
            continue
        tolerance = 0.02 * actual.abs().clip(lower=1)
        matches = (expected - actual).abs() <= tolerance
        rate = float(matches[informative].mean())
        if rate >= 0.95:
            found.append({"formula": f"{a} × {b} ≈ {c}", "left_columns": [a, b], "target_column": c,
                          "checked_rows": int(len(frame)), "informative_rows": informative_count,
                          "match_rate": round(rate, 4), "mismatch_rows": int((~matches).sum())})
    found.sort(key=lambda item: (-item["match_rate"], item["mismatch_rows"]))
    unique, seen = [], set()
    for item in found:
        if item["target_column"] in seen:
            continue
        seen.add(item["target_column"]); unique.append(item)
    return unique[:3]


def scan_dataset(df: pd.DataFrame, *, age_types: dict[str, str] | None = None) -> dict[str, Any]:
    columns: dict[str, dict[str, Any]] = {}
    numeric_series: dict[str, pd.Series] = {}
    for column in df.columns:
        name = str(column)
        info, numeric = _scan_column(name, df[column], len(df), (age_types or {}).get(name))
        columns[name] = info
        if numeric is not None:
            numeric_series[name] = numeric
    identifier_columns = [n for n, i in columns.items() if i.get("key_candidate")]
    identifier_duplicates = {}
    for name in identifier_columns:
        non_null = df[name].dropna()
        involved = int(non_null.duplicated(keep=False).sum())
        removable = int(non_null.duplicated(keep="first").sum())
        if involved:
            identifier_duplicates[name] = {"duplicate_rows_involved": involved, "duplicate_rows_to_remove_if_key_were_safe": removable}
    digest = {"rows": int(len(df)), "columns_count": int(df.shape[1]),
              "full_duplicate_rows_to_remove": int(df.duplicated(keep="first").sum()),
              "identifier_columns": identifier_columns, "identifier_duplicates": identifier_duplicates, "columns": columns}
    relationships = _find_relationships(numeric_series) if len(numeric_series) >= 3 else []
    if relationships:
        digest["relationships"] = relationships
    return digest


def build_requirements(digest):
    requirements = []
    counter = 0

    def add(column, issue, operations, *, review_required=False, required_tokens=None):
        nonlocal counter
        counter += 1
        allowed = sorted(set(operations) | {"no_change"})
        requirements.append({"id": f"R{counter:03d}", "column": column, "issue": issue, "use_one_of": allowed,
                             "review_required": bool(review_required), "required_tokens": [str(v) for v in (required_tokens or [])]})

    duplicates = int(digest.get("full_duplicate_rows_to_remove", 0) or 0)
    if duplicates:
        add(None, f"{duplicates} fully duplicated rows", ["drop_duplicate_rows"])

    for name, info in (digest.get("columns") or {}).items():
        kind = info.get("kind")
        if info.get("whitespace"):
            add(name, f"{info['whitespace']} values with leading/trailing spaces", ["strip_whitespace"])
        if info.get("null_like"):
            tokens = list((info.get("null_like") or {}).keys())
            add(name, f"null-like placeholders: {tokens[:8]}", ["replace_null_like", "replace_values"], required_tokens=tokens)
        if kind == "numeric":
            format_flags = [k for k in ("currency", "thousands_sep", "decimal_comma") if info.get(k)]
            if format_flags and not info.get("identifier_like"):
                add(name, f"numeric formatting requires conversion ({', '.join(format_flags)})", ["to_numeric"])
            if info.get("unparseable") and not info.get("identifier_like"):
                bad_tokens = list((info.get("unparseable") or {}).keys())
                add(name, f"unparseable values inside a mostly numeric column: {bad_tokens[:10]}",
                    ["replace_values", "replace_null_like"], required_tokens=bad_tokens)
            if (not info.get("identifier_like") and float(info.get("numeric_share", 0) or 0) >= 0.5
                    and (info.get("unparseable") or format_flags)):
                add(name, "mostly numeric values stored in a non-numeric column", ["to_numeric"])
            if info.get("implausible_age"):
                policy = info.get("age_policy") or age_policy_for_column(name)
                upper = policy["maximum"] if policy else None
                bounds = "<0 or >120" if upper is not None else "<0 only; no upper bound"
                kind = policy["kind"] if policy else "unknown"
                add(name, f"{info['implausible_age']} {kind} ages outside review bounds ({bounds})",
                    ["replace_null_like"], review_required=True,
                    required_tokens=info.get("implausible_age_tokens"))
            if info.get("negative") and not info.get("age_policy"):
                strictly_positive = bool(NON_NEGATIVE_NAME_RE.search(name))
                add(name, f"{info['negative']} negative numeric values", ["set_negative_to_null"], review_required=not strictly_positive)
        if kind == "date":
            mixed_formats = len(info.get("date_formats", {}) or {}) > 1
            invalid_dates = bool(info.get("invalid_dates"))
            if mixed_formats or invalid_dates:
                add(name, "mixed date formats and/or invalid dates", ["to_datetime"], review_required=invalid_dates)
        if kind == "email":
            if info.get("uppercase"):
                add(name, f"{info['uppercase']} email values contain uppercase letters", ["normalize_case"])
            if info.get("invalid_format"):
                add(name, f"{info['invalid_format']['count']} malformed email values", ["replace_values"], review_required=True)
        if kind == "categorical":
            if info.get("case_variants"):
                add(name, "case variants of categorical values", ["normalize_case", "replace_values"])
            if info.get("punctuation_variants"):
                add(name, "punctuation/spacing variants of categorical values", ["replace_values"])
            if info.get("probable_typos"):
                add(name, f"probable category typos: {info['probable_typos']}", ["replace_values"])
            if COUNTRY_NAME_RE.search(name) and (info.get("mixed_country_codes_and_names") or info.get("punctuation_variants") or info.get("probable_typos")):
                add(name, "country vocabulary mixes codes, aliases, translations or variants", ["replace_values"])
        if kind == "text" and info.get("name_case_inconsistent"):
            add(name, f"{info['name_case_inconsistent']['count']} person-name values have inconsistent case", ["normalize_case"], review_required=True)
        if info.get("format_patterns") and info.get("identifier_like"):
            add(name, "identifier/phone values use inconsistent formats", ["replace_values"], review_required=True)

    # --- relations entre colonnes (HORS de la boucle des colonnes) ---
    for relation in digest.get("relationships", []) or []:
        mismatch_rows = int(relation.get("mismatch_rows", 0) or 0)
        if mismatch_rows <= 0:
            continue
        add(
            str(relation.get("target_column")),
            f"{mismatch_rows} rows violate likely relationship {relation.get('formula')}",
            ["recalculate_from_columns"],
            review_required=True,
        )

    # --- clés répétées ---
    for column, info in (digest.get("identifier_duplicates") or {}).items():
        add(column, f"{info['duplicate_rows_involved']} rows share repeated identifier values; exact duplicates vs conflicts must be distinguished",
            ["drop_duplicates_by_columns"], review_required=True)

    return requirements


def _targets(action):
    targets = set()
    if action.get("column"):
        targets.add(str(action["column"]))
    for item in action.get("columns") or []:
        if item:
            targets.add(str(item))
    return targets


def _replacement_old_values(action):
    return {str(i.get("old_value")).strip().casefold() for i in (action.get("replacements") or []) if isinstance(i, dict) and i.get("old_value") is not None}


def _null_tokens(action):
    return {str(v).strip().casefold() for v in (action.get("null_tokens") or [])}


def check_coverage(actions, requirements):
    missing = []
    for requirement in requirements:
        req_column = requirement.get("column")
        allowed = set(requirement.get("use_one_of", []))
        review_required = bool(requirement.get("review_required", False))
        required_tokens = {str(v).strip().casefold() for v in (requirement.get("required_tokens") or []) if str(v).strip()}
        matching = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            operation = str(action.get("operation", ""))
            if operation not in allowed:
                continue
            targets = _targets(action)
            if req_column is not None and str(req_column) not in targets:
                continue
            if operation == "no_change":
                if bool(action.get("requires_review", False)):
                    matching.append(action)
                continue
            if review_required and not bool(action.get("requires_review", False)):
                continue
            matching.append(action)
        covered = False
        if any(str(a.get("operation")) == "no_change" for a in matching):
            covered = True
        elif matching and not required_tokens:
            covered = True
        elif matching and required_tokens:
            provided = set()
            for a in matching:
                op = str(a.get("operation", ""))
                if op == "replace_null_like":
                    provided |= _null_tokens(a)
                elif op == "replace_values":
                    provided |= _replacement_old_values(a)
            covered = required_tokens.issubset(provided)
        if not covered:
            missing.append({"id": requirement.get("id"), "column": requirement.get("column") or "(whole dataset)", "issue": requirement.get("issue"),
                            "use_one_of": requirement.get("use_one_of"), "review_required": requirement.get("review_required", False),
                            "required_tokens": requirement.get("required_tokens", [])})
    return missing


def digest_summary(digest, requirements):
    return (f"{digest['columns_count']} colonnes × {digest['rows']:,} lignes analysées localement · {len(requirements)} exigences de qualité").replace(",", " ")
