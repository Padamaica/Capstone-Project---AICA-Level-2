"""Build templates/MIS_Input_Template.xlsx (blank, with instructions) and
input/MIS_Input_Sample_Sep-2026.xlsx (full synthetic data for demos)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
NAVY, LIGHT, YELLOW = "1F3864", "D9E2F3", "FFF2CC"
HDR_FONT = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
HDR_FILL = PatternFill("solid", fgColor=NAVY)
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

PL_CATS = ["Revenue", "Other Income", "COGS", "Employee Cost", "Admin Expenses", "Marketing Expenses",
           "Depreciation", "Finance Cost", "Tax"]
BS_CATS = ["Fixed Assets", "Receivables", "Inventory", "Other Current Assets", "Cash & Bank", "Payables",
           "Statutory Dues", "Other Current Liabilities", "Borrowings", "Share Capital"]

GL_COLS = [("date", "Voucher date (DD-MM-YYYY or YYYY-MM-DD)", 13), ("voucher_no", "Voucher number", 20),
           ("voucher_type", "Sales / Purchase / Receipt / Payment / Journal", 14), ("account", "Ledger name (must exist in Mapping)", 28),
           ("party", "Customer / vendor name (needed for ageing)", 24), ("debit", "Debit amount (INR)", 15),
           ("credit", "Credit amount (INR)", 15), ("cost_center", "Plant / dept (optional)", 12),
           ("narration", "Narration (write 'Opening' on opening-balance voucher)", 40)]


def header(ws, cols, row=1):
    for i, (name, *_rest) in enumerate(cols, 1):
        c = ws.cell(row=row, column=i, value=name)
        c.font, c.fill, c.border = HDR_FONT, HDR_FILL, BOX
        c.alignment = Alignment(horizontal="center", vertical="center")
        if len(_rest) > 1:
            ws.column_dimensions[get_column_letter(i)].width = _rest[1]
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def notes_row(ws, cols, row=2):
    pass


def write_df(ws, df, start_row=2, num_cols=(), date_cols=()):
    for r, rec in enumerate(df.itertuples(index=False), start_row):
        for c, v in enumerate(rec, 1):
            cell = ws.cell(row=r, column=c, value=v)
            col = df.columns[c - 1]
            if col in num_cols:
                cell.number_format = "#,##,##0.00"
            if col in date_cols:
                cell.number_format = "DD-MMM-YYYY"


def readme(ws, title):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 95
    ws["B2"] = title
    ws["B2"].font = Font(bold=True, size=16, color=NAVY)
    ws["B3"] = "AI Finance Co-Pilot: monthly input workbook. Fill 3 sheets, save in the input folder, run RUN_MIS.bat."
    ws["B3"].font = Font(italic=True, color="595959")
    rows = [
        ("STEP 1", "GL sheet: paste the Day Book / GL export for ALL months from the start of the FY (or with an opening-balance voucher)."),
        ("STEP 2", "Budget sheet: one row per month per P&L category (amounts positive). Optional, but needed for Budget vs Actual."),
        ("STEP 3", "Mapping sheet: every ledger in the GL must appear once with its category (use the dropdown). New ledger = add one row."),
        ("STEP 4", "Save as  MIS_Input_<Mon-YYYY>.xlsx  inside the  input  folder of the tool."),
        ("STEP 5", "Double-click RUN_MIS.bat. Reports appear in output\\<YYYY-MM>\\ (Excel MIS, PDF board pack, AI commentary)."),
        ("", ""),
        ("GL rules", "Each voucher must balance (total debit = total credit). Debit/credit as positive numbers; no subtotal rows; no blank ledger names."),
        ("Single amount column?", "Also accepted: columns 'amount' + 'Dr/Cr' instead of debit/credit. Tally/Zoho/SAP column names are auto-recognised."),
        ("Party ledgers", "Customers map to 'Receivables', vendors to 'Payables' (or use control ledgers Sundry Debtors / Creditors + party column)."),
        ("Opening balances", "Put opening balances in one Journal voucher with the word 'Opening' in narration (not treated as cash flow)."),
        ("If the run stops", "Open output\\VALIDATION_ERRORS.txt. It lists unmapped ledgers / unbalanced vouchers to fix."),
        ("Data privacy", "Everything runs on this computer. The AI model is local (Ollama); names are masked before AI sees them."),
        ("", ""),
        ("P&L categories", ", ".join(PL_CATS)),
        ("BS categories", ", ".join(BS_CATS)),
    ]
    for i, (k, v) in enumerate(rows, 5):
        ws.cell(row=i, column=2, value=k).font = Font(bold=True, color=NAVY)
        c = ws.cell(row=i, column=3, value=v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if k.startswith("STEP"):
            ws.cell(row=i, column=2).fill = PatternFill("solid", fgColor=YELLOW)


def lists_sheet(wb):
    ws = wb.create_sheet("Lists")
    ws["A1"], ws["B1"], ws["C1"] = "category", "statement", "statement_codes"
    for i, c in enumerate(PL_CATS + BS_CATS, 2):
        ws.cell(row=i, column=1, value=c)
        ws.cell(row=i, column=2, value="PL" if c in PL_CATS else "BS")
    ws["C2"], ws["C3"] = "PL", "BS"
    ws.sheet_state = "hidden"
    return len(PL_CATS + BS_CATS) + 1


def mapping_sheet(wb, mapping: pd.DataFrame, n_cats: int, extra_rows: int = 200):
    ws = wb.create_sheet("Mapping")
    header(ws, [("account", "", 32), ("category", "", 26), ("statement", "", 12)])
    write_df(ws, mapping)
    last = len(mapping) + 1 + extra_rows
    dv = DataValidation(type="list", formula1=f"=Lists!$A$2:$A${n_cats}", allow_blank=True,
                        error="Pick a category from the list", showErrorMessage=True)
    dv2 = DataValidation(type="list", formula1='"PL,BS"', allow_blank=True)
    ws.add_data_validation(dv)
    ws.add_data_validation(dv2)
    dv.add(f"B2:B{last}")
    dv2.add(f"C2:C{last}")


def build(path: Path, gl: pd.DataFrame, budget: pd.DataFrame, mapping: pd.DataFrame, title: str):
    wb = Workbook()
    readme(wb.active, title)
    wb.active.title = "README"
    ws = wb.create_sheet("GL")
    header(ws, GL_COLS)
    write_df(ws, gl, num_cols=("debit", "credit"), date_cols=("date",))
    ws.auto_filter.ref = f"A1:I{max(len(gl) + 1, 2)}"
    wsb = wb.create_sheet("Budget")
    header(wsb, [("month", "", 12), ("category", "", 24), ("amount", "", 16)])
    write_df(wsb, budget, num_cols=("amount",))
    n = lists_sheet(wb)
    mapping_sheet(wb, mapping, n)
    wb.move_sheet("Lists", offset=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"written {path}  (GL rows {len(gl):,})")


def main():
    mapping = pd.read_csv(ROOT / "config/coa_mapping.csv")
    gl = pd.read_csv(ROOT / "data/sample/gl.csv", parse_dates=["date"])
    bud = pd.read_csv(ROOT / "data/sample/budget.csv")
    # blank template: 2 illustrative balanced vouchers
    ex = pd.DataFrame([
        ["2026-10-03", "SL/2026-27/0001", "Sales", "Sundry Debtors", "Apex Retail Ltd", 118000, 0, "Plant-1", "Invoice 101"],
        ["2026-10-03", "SL/2026-27/0001", "Sales", "Sales - Domestic", "", 0, 100000, "Plant-1", "Invoice 101"],
        ["2026-10-03", "SL/2026-27/0001", "Sales", "Output GST", "", 0, 18000, "Plant-1", "Invoice 101"],
        ["2026-10-10", "RC/2026-27/0001", "Receipt", "HDFC Bank Current A/c", "", 118000, 0, "HO", "Received against Inv 101"],
        ["2026-10-10", "RC/2026-27/0001", "Receipt", "Sundry Debtors", "Apex Retail Ltd", 0, 118000, "HO", "Received against Inv 101"],
    ], columns=[c[0] for c in GL_COLS])
    ex["date"] = pd.to_datetime(ex["date"])
    ex_bud = pd.DataFrame([["2026-10", c, 0] for c in PL_CATS], columns=["month", "category", "amount"])
    build(ROOT / "templates/MIS_Input_Template.xlsx", ex, ex_bud, mapping, "MIS Input Template")
    build(ROOT / "input/MIS_Input_Sample_Sep-2026.xlsx", gl[[c[0] for c in GL_COLS]], bud, mapping,
          "MIS Input: SAMPLE DATA (synthetic) Apr-2025 to Sep-2026")


if __name__ == "__main__":
    sys.exit(main())
