import csv
import io
import re
from pathlib import Path

import pandas as pd


HEADER_HINTS = {
    "id", "date", "name", "country", "pays", "nation", "city",
    "population", "sales", "price", "amount", "quantity", "category",
    "product", "customer", "client", "email", "phone", "currency",
    "rate", "salary", "department", "status", "observation",
}


def _is_empty(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip() == ""


def _numeric_like(value) -> bool:
    if _is_empty(value):
        return False
    text = str(value).strip().replace(" ", "")
    return bool(re.fullmatch(r"-?\d+(?:[.,]\d+)?", text))


def _header_hint_score(value) -> int:
    if _is_empty(value):
        return 0
    words = re.findall(r"[A-Za-zÀ-ÿ]+", str(value).casefold())
    return sum(word in HEADER_HINTS for word in words)


def detect_header_row(preview: pd.DataFrame) -> int:
    if preview.empty:
        return 0

    total_columns = max(preview.shape[1], 1)
    max_rows = min(10, len(preview))
    scores = []

    for index in range(max_rows):
        values = [v for v in preview.iloc[index].tolist() if not _is_empty(v)]
        if not values:
            scores.append((index, -100.0))
            continue

        filled = len(values)
        occupancy = filled / total_columns
        text_count = sum(any(ch.isalpha() for ch in str(v)) for v in values)
        numeric_count = sum(_numeric_like(v) for v in values)
        hints = sum(_header_hint_score(v) for v in values)
        text_ratio = text_count / filled
        numeric_ratio = numeric_count / filled

        score = (
            occupancy * 5
            + text_ratio * 2.5
            + hints * 0.9
            - numeric_ratio * 2
            - index * 0.05
        )
        scores.append((index, score))

    # Common pattern: first row is a report title, second row is the true header.
    if len(preview) >= 2 and total_columns > 1:
        first_filled = sum(not _is_empty(v) for v in preview.iloc[0])
        second_filled = sum(not _is_empty(v) for v in preview.iloc[1])
        if (first_filled / total_columns) < 0.50 and (second_filled / total_columns) >= 0.65:
            return 1

    return max(scores, key=lambda item: item[1])[0]


def _detect_encoding(file_bytes: bytes):
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            return file_bytes.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Encodage impossible à détecter : {last_error}")


def _detect_separator(text: str) -> str:
    candidates = [",", ";", "\t", "|"]
    lines = [line for line in text.splitlines() if line.strip()][:30]
    if not lines:
        return ","

    best_separator = ","
    best_score = -1

    for separator in candidates:
        counts = []
        try:
            reader = csv.reader(lines, delimiter=separator)
            counts = [len(row) for row in reader]
        except csv.Error:
            continue

        useful = [count for count in counts if count > 1]
        if not useful:
            continue

        frequencies = {}
        for count in useful:
            frequencies[count] = frequencies.get(count, 0) + 1

        mode = max(frequencies, key=frequencies.get)
        score = frequencies[mode] * 10 + mode
        if score > best_score:
            best_score = score
            best_separator = separator

    return best_separator


def _raw_display_from_rows(rows):
    if not rows:
        return pd.DataFrame()

    max_columns = max(len(row) for row in rows)
    padded = [list(row) + [""] * (max_columns - len(row)) for row in rows]
    raw = pd.DataFrame(
        padded,
        columns=[f"Colonne {i + 1}" for i in range(max_columns)],
    )

    for column in raw.columns:
        raw[column] = (
            raw[column]
            .astype("string")
            .fillna("")
            .str.replace("\r", " ↵ ", regex=False)
            .str.replace("\n", " ↵ ", regex=False)
        )
    return raw


def _read_csv(file_bytes: bytes):
    decoded, encoding = _detect_encoding(file_bytes)
    separator = _detect_separator(decoded)

    rows = list(csv.reader(io.StringIO(decoded), delimiter=separator))
    raw = _raw_display_from_rows(rows)

    preview = pd.read_csv(
        io.StringIO(decoded),
        sep=separator,
        header=None,
        nrows=12,
        dtype="string",
        engine="python",
    )
    header_row = detect_header_row(preview)

    df = pd.read_csv(
        io.StringIO(decoded),
        sep=separator,
        header=header_row,
        engine="python",
    )

    df = (
        df.dropna(axis=0, how="all")
        .dropna(axis=1, how="all")
        .reset_index(drop=True)
    )

    metadata = {
        "file_type": "csv",
        "encoding": encoding,
        "separator": separator,
        "header_row": int(header_row),
    }
    return df, raw, metadata


def _read_excel(file_bytes: bytes, suffix: str):
    engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
    excel = pd.ExcelFile(io.BytesIO(file_bytes), engine=engine)
    if not excel.sheet_names:
        raise ValueError("Le fichier Excel ne contient aucune feuille.")

    sheet_name = excel.sheet_names[0]
    preview = pd.read_excel(
        io.BytesIO(file_bytes),
        sheet_name=sheet_name,
        header=None,
        nrows=12,
        engine=engine,
    )
    header_row = detect_header_row(preview)

    raw_full = pd.read_excel(
        io.BytesIO(file_bytes),
        sheet_name=sheet_name,
        header=None,
        engine=engine,
        dtype=object,
    )
    raw_rows = raw_full.fillna("").astype(str).values.tolist()
    raw = _raw_display_from_rows(raw_rows)

    df = pd.read_excel(
        io.BytesIO(file_bytes),
        sheet_name=sheet_name,
        header=header_row,
        engine=engine,
    )
    df = (
        df.dropna(axis=0, how="all")
        .dropna(axis=1, how="all")
        .reset_index(drop=True)
    )

    metadata = {
        "file_type": suffix.lstrip("."),
        "sheet_name": sheet_name,
        "sheet_names": excel.sheet_names,
        "header_row": int(header_row),
    }
    return df, raw, metadata


def read_tabular_file(file_bytes: bytes, filename: str):
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return _read_csv(file_bytes)
    if suffix in {".xlsx", ".xls"}:
        return _read_excel(file_bytes, suffix)
    raise ValueError("Format non supporté. Utilisez CSV, XLSX ou XLS.")
