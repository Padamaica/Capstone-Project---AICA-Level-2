"""Single-workbook input: one Excel file with sheets GL, Budget, Mapping (see templates/MIS_Input_Template.xlsx).

This lets the month-end user do just one thing: export the ledger into the template and drop it in input/.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

SHEET_ALIASES = {
    "gl": ["gl", "general ledger", "day book", "daybook", "ledger", "gl data"],
    "budget": ["budget", "budgets", "plan"],
    "mapping": ["mapping", "coa", "coa mapping", "ledger mapping", "chart of accounts"],
}


@dataclass
class WorkbookParts:
    gl: io.BytesIO
    budget: io.BytesIO | None
    mapping: io.BytesIO | None
    sheets_found: dict


def _as_csv(df: pd.DataFrame, name: str) -> io.BytesIO:
    df = df.dropna(how="all")
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    if "month" in [str(c).strip().lower() for c in df.columns]:  # Excel may turn 2026-09 into a date
        col = [c for c in df.columns if str(c).strip().lower() == "month"][0]
        df[col] = pd.to_datetime(df[col].astype(str), errors="coerce").dt.strftime("%Y-%m")
    buf = io.BytesIO(df.to_csv(index=False).encode("utf-8"))
    buf.name = name
    return buf


def split_input_workbook(src) -> WorkbookParts:
    xl = pd.ExcelFile(src)
    lookup = {s.strip().lower(): s for s in xl.sheet_names}
    found = {}
    for key, aliases in SHEET_ALIASES.items():
        found[key] = next((lookup[a] for a in aliases if a in lookup), None)
    if not found["gl"]:
        raise ValueError(f"Workbook needs a sheet named 'GL'. Sheets found: {xl.sheet_names}")
    gl = _as_csv(xl.parse(found["gl"]), "gl.csv")
    bud = _as_csv(xl.parse(found["budget"]), "budget.csv") if found["budget"] else None
    mp = _as_csv(xl.parse(found["mapping"]), "mapping.csv") if found["mapping"] else None
    return WorkbookParts(gl, bud, mp, found)


def latest_input_file(folder: Path) -> Path:
    files = [p for p in folder.glob("*.xlsx") if not p.name.startswith("~$")]
    if not files:
        raise FileNotFoundError(f"No .xlsx file found in {folder}. Copy your filled template there.")
    return max(files, key=lambda p: p.stat().st_mtime)
