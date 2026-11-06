#!/usr/bin/env python3
"""Write one comparison result into the tracking sheet.

The sheet has a header row with the columns Benchmark, GitHub Account, Github PR
and Verification (found by name, in any order). The row is found by the pull
request URL; if there is none, a row is added. Verification is overwritten.
Benchmark and GitHub Account are written only when they are empty, so a value
that a person typed stays.

Needs GOOGLE_SERVICE_ACCOUNT_JSON (the key of a service account that can edit the
sheet), SHEET_ID and SHEET_TAB. Without the key it prints the plan and exits 0.
"""
import argparse
import json
import os
import sys

COLUMNS = {
    "benchmark": "benchmark",
    "account": "github account",
    "pr": "github pr",
    "verification": "verification",
}


def column_letter(index):
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def find_columns(header):
    names = [str(h).strip().lower() for h in header]
    cols = {}
    for key, name in COLUMNS.items():
        if name not in names:
            raise ValueError(f"the sheet header has no '{name}' column: {header}")
        cols[key] = names.index(name)
    return cols


def norm_url(url):
    return str(url).strip().rstrip("/").lower()


def plan_update(rows, result):
    """Return {"row": int|None, "updates": [(a1, value)], "append": list|None}."""
    if not rows:
        raise ValueError("the sheet is empty; it needs a header row")
    cols = find_columns(rows[0])
    values = {
        "benchmark": result["benchmark"],
        "account": f"@{result['author']}" if result.get("author") else "",
        "pr": result["pr_url"],
        "verification": result["cell"],
    }

    def cell(row, key):
        return row[cols[key]].strip() if len(row) > cols[key] else ""

    for number, row in enumerate(rows[1:], start=2):
        if norm_url(cell(row, "pr")) == norm_url(result["pr_url"]):
            updates = [(f"{column_letter(cols['verification'])}{number}", values["verification"])]
            for key in ("benchmark", "account"):
                if not cell(row, key) and values[key]:
                    updates.append((f"{column_letter(cols[key])}{number}", values[key]))
            return {"row": number, "updates": updates, "append": None}

    new_row = [""] * (max(cols.values()) + 1)
    for key, value in values.items():
        new_row[cols[key]] = value
    return {"row": None, "updates": [], "append": new_row}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True, help="result.json from report.py")
    args = ap.parse_args()
    result = json.loads(open(args.result).read())

    key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not key:
        print("GOOGLE_SERVICE_ACCOUNT_JSON is not set; the sheet is not changed. Cell text:")
        print(result["cell"])
        return 0

    import gspread  # installed by the workflow step

    client = gspread.service_account_from_dict(json.loads(key))
    sheet = client.open_by_key(os.environ["SHEET_ID"]).worksheet(os.environ.get("SHEET_TAB", "Sheet1"))
    plan = plan_update(sheet.get_all_values(), result)
    if plan["append"] is not None:
        sheet.append_row(plan["append"], value_input_option="RAW", table_range="A1")
        print(f"Added a row for {result['pr_url']}")
    for a1, value in plan["updates"]:
        sheet.update(range_name=a1, values=[[value]], value_input_option="RAW")
    if plan["updates"]:
        print(f"Updated row {plan['row']}: {[a1 for a1, _ in plan['updates']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
