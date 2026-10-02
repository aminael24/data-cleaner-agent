import io

import pandas as pd

from core.audit import profile_dataset
from core.cleaning_engine import execute_cleaning_plan
from core.csv_loader import read_tabular_file


def main():
    csv_text = (
        'Report title,,,,\n'
        'Observation,Country,"Population\n(M)",Price,Name\n'
        '1,Austria,"8,4",$389.54," A "\n'
        '4,Czech Rep.,"10,2",793 USD,B\n'
    )

    df, raw, meta = read_tabular_file(csv_text.encode("utf-8"), "sample.csv")
    assert meta["header_row"] == 1
    assert not raw.empty
    assert profile_dataset(df)["header_issues"]

    plan = {
        "actions": [
            {"operation": "normalize_column_names", "reason": "headers"},
            {
                "operation": "to_numeric",
                "columns": ["Population\n(M)", "Price"],
                "decimal_comma": True,
                "reason": "numbers",
            },
            {
                "operation": "strip_whitespace",
                "columns": ["Name"],
                "reason": "spaces",
            },
        ]
    }

    cleaned, _ = execute_cleaning_plan(df, plan)
    assert abs(float(cleaned.loc[0, "Price"]) - 389.54) < 1e-9
    assert abs(float(cleaned.loc[1, "Price"]) - 793.0) < 1e-9
    assert abs(float(cleaned.loc[0, "Population (M)"]) - 8.4) < 1e-9
    assert cleaned.loc[0, "Name"] == "A"

    excel_buffer = io.BytesIO()
    raw_excel = pd.DataFrame([
        ["Report", None, None],
        ["ID", "Country", "Value"],
        [1, "Austria", 8.4],
        [2, "France", 9.1],
    ])
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        raw_excel.to_excel(writer, index=False, header=False)

    excel_df, _, excel_meta = read_tabular_file(excel_buffer.getvalue(), "sample.xlsx")
    assert excel_meta["header_row"] == 1
    assert list(excel_df.columns) == ["ID", "Country", "Value"]

    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()
