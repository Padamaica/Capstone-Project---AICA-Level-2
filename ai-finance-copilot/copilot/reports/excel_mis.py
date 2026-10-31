"""Board-ready Excel MIS pack (openpyxl): formatted, Indian number format, charts, conditional colours."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..config import settings
from ..engine.statements import ytd_columns
from ..utils import fmt_inr, month_label

INR_FMT = r'[>=10000000]##\,##\,##\,##0;[>=100000]##\,##\,##0;##,##0'
NAVY, LIGHT, GREEN, RED, AMBER = "1F3864", "D9E1F2", "C6EFCE", "FFC7CE", "FFEB9C"
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
SUBTOTALS = {"Gross Profit", "EBITDA", "EBIT", "PBT", "PAT", "Total Assets", "Total Liabilities", "Total Equity",
             "Total Liabilities & Equity", "Cash from Operations (CFO)", "Cash from Financing (CFF)", "Net Change in Cash",
             "Closing Cash", "Free Cash Flow (CFO + CFI)", "TOTAL"}


def _title(ws, text: str, sub: str = "") -> int:
    ws["A1"] = text
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    ws["A2"] = sub or f"{settings.company_name} | Amounts in {settings.currency}"
    ws["A2"].font = Font(italic=True, color="595959")
    return 4


def _write_df(ws, df: pd.DataFrame, row: int, col: int = 1, index: bool = True, pct_rows: set | None = None,
              num_fmt: str = INR_FMT, header_labels: list[str] | None = None) -> int:
    d = df.reset_index() if index else df
    headers = header_labels or [str(c) for c in d.columns]
    for j, h in enumerate(headers):
        c = ws.cell(row=row, column=col + j, value=h)
        c.font, c.fill, c.alignment, c.border = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=NAVY), \
            Alignment(horizontal="center", wrap_text=True), BORDER
    for i, rec in enumerate(d.itertuples(index=False), start=1):
        label = str(rec[0])
        is_sub = label in SUBTOTALS or label.startswith("Check")
        for j, v in enumerate(rec):
            if isinstance(v, float) and pd.isna(v):
                v = None
            c = ws.cell(row=row + i, column=col + j, value=v.item() if hasattr(v, "item") else v)
            c.border = BORDER
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                c.number_format = "0.00" if (pct_rows and label in pct_rows) else num_fmt
            if is_sub:
                c.font = Font(bold=True)
                c.fill = PatternFill("solid", fgColor=LIGHT)
    return row + len(d) + 2


def _autowidth(ws, first: int = 34, other: int = 14) -> None:
    ws.column_dimensions["A"].width = first
    for i in range(2, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(i)].width = other
    ws.freeze_panes = "B5"


def build_excel_mis(res, path: Path) -> Path:
    wb = Workbook()
    m, months = res.month, res.months
    ytd = ytd_columns(months, m, settings.fy_start_month)
    prev = months[-2] if len(months) > 1 else m

    # ---------------- Summary
    ws = wb.active
    ws.title = "Summary"
    r = _title(ws, f"MIS Summary: {month_label(m)}")
    kpis = [("Revenue", "pnl"), ("Gross Profit", "pnl"), ("EBITDA", "pnl"), ("PAT", "pnl")]
    rows = []
    for k, _ in kpis:
        cur, pv = float(res.pnl.loc[k, m]), float(res.pnl.loc[k, prev])
        rows.append([k, cur, pv, (cur - pv) / abs(pv) * 100 if pv else None, float(res.pnl.loc[k, ytd].sum())])
    for k in ["Gross Margin %", "EBITDA Margin %", "PAT Margin %", "DSO (days)", "DPO (days)", "Current Ratio (x)", "Cash & Bank"]:
        cur, pv = float(res.ratios.loc[k, m]), float(res.ratios.loc[k, prev])
        rows.append([k, cur, pv, cur - pv if "Cash" not in k else (cur - pv) / abs(pv) * 100 if pv else None, None])
    kdf = pd.DataFrame(rows, columns=["KPI", month_label(m), month_label(prev), "Change (% / pts)", f"YTD ({month_label(ytd[0])}-)"])
    pct_like = {"Gross Margin %", "EBITDA Margin %", "PAT Margin %", "DSO (days)", "DPO (days)", "Current Ratio (x)"}
    r = _write_df(ws, kdf, r, index=False, pct_rows=pct_like)
    for rr in range(5, 5 + len(kdf)):
        ws.cell(row=rr, column=4).number_format = '+0.0;-0.0;0.0'
    ws.cell(row=r, column=1, value=f"Management Commentary  (source: {res.commentary.get('source', 'n/a')})").font = Font(bold=True, size=12, color=NAVY)
    r += 1
    for line in (res.commentary.get("text") or "").splitlines():
        c = ws.cell(row=r, column=1, value=line.replace("### ", "").replace("**", ""))
        if line.startswith("###"):
            c.font = Font(bold=True, color=NAVY)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = 15 if len(line) < 110 else 30 * (len(line) // 110 + 1) / 2
        r += 1
    ws.column_dimensions["A"].width = 30
    for col in "BCDE":
        ws.column_dimensions[col].width = 18

    # ---------------- P&L
    ws = wb.create_sheet("P&L")
    r = _title(ws, "Profit & Loss: Monthly")
    p = res.pnl.copy()
    p[f"YTD {ytd[0]}..{ytd[-1]}"] = p[ytd].sum(axis=1)
    p.index.name = "Particulars"
    end = _write_df(ws, p, r)
    _autowidth(ws)
    ch = LineChart()
    ch.title, ch.height, ch.width = "Revenue, EBITDA & PAT trend", 8, 22
    for row_idx in (r + 1, r + 7, r + 14):  # Revenue, EBITDA, PAT
        ch.add_data(Reference(ws, min_col=1, max_col=len(months) + 1, min_row=row_idx), from_rows=True, titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=2, max_col=len(months) + 1, min_row=r))
    ch.y_axis.numFmt = INR_FMT
    ws.add_chart(ch, f"B{end + 1}")

    # ---------------- Balance Sheet / Cash Flow / Ratios
    for name, df, title in [("Balance Sheet", res.balance_sheet, "Balance Sheet: Month-end"),
                            ("Cash Flow", res.cash_flow, "Cash Flow Statement (Indirect)")]:
        ws = wb.create_sheet(name)
        r = _title(ws, title)
        d = df.copy()
        d.index.name = "Particulars"
        _write_df(ws, d, r)
        _autowidth(ws)
    ws = wb.create_sheet("Ratios")
    r = _title(ws, "Key Ratios & KPIs")
    d = res.ratios.copy()
    d.index.name = "Ratio"
    _write_df(ws, d, r, pct_rows=set(d.index) - {"Working Capital", "Cash & Bank"})
    _autowidth(ws)

    # ---------------- Budget vs Actual
    if res.bva_month is not None:
        ws = wb.create_sheet("Budget vs Actual")
        r = _title(ws, f"Budget vs Actual: {month_label(m)} and YTD", f"Flag = |variance| >= {settings.variance_threshold_pct}%")
        for label, df in (("Month", res.bva_month), ("YTD", res.bva_ytd)):
            ws.cell(row=r, column=1, value=label).font = Font(bold=True, size=12, color=NAVY)
            d = df.rename(columns={"line_item": "Line item", "budget": "Budget", "actual": "Actual", "variance": "Variance",
                                   "variance_pct": "Variance %", "status": "Status", "flag": "Flag"})
            start = r + 1
            r = _write_df(ws, d, start, index=False, pct_rows=set(d["Line item"]) if False else None)
            for i, rec in enumerate(d.itertuples(index=False), start=start + 1):
                ws.cell(row=i, column=5).number_format = "+0.0;-0.0;0.0"
                fill = GREEN if rec.Status == "Favourable" else (RED if rec.Flag else AMBER)
                ws.cell(row=i, column=6).fill = PatternFill("solid", fgColor=fill)
        _autowidth(ws, 26, 16)
        ws.freeze_panes = None

    # ---------------- Ageing
    for name, summ, det in (("AR Ageing", res.ar_summary, res.ar_detail), ("AP Ageing", res.ap_summary, res.ap_detail)):
        ws = wb.create_sheet(name)
        r = _title(ws, f"{name} as of {month_label(m)} (FIFO)")
        r = _write_df(ws, summ.rename(columns={"party": "Party"}), r, index=False)
        bc = BarChart()
        bc.type, bc.grouping, bc.overlap, bc.title, bc.height, bc.width = "bar", "stacked", 100, f"{name} by bucket", 8, 18
        n = len(summ) - 1  # exclude TOTAL row
        if n > 0:
            bc.add_data(Reference(ws, min_col=2, max_col=6, min_row=4, max_row=4 + n), titles_from_data=True)
            bc.set_categories(Reference(ws, min_col=1, min_row=5, max_row=4 + n))
            ws.add_chart(bc, "J4")
        ws.cell(row=r, column=1, value="Open items").font = Font(bold=True, color=NAVY)
        _write_df(ws, det.rename(columns=str.title), r + 1, index=False)
        _autowidth(ws, 28, 14)

    # ---------------- Anomalies / Forecast / Data quality
    ws = wb.create_sheet("Anomalies")
    r = _title(ws, "Anomalies & Control Exceptions", "Review before closing the books")
    a = res.anomalies.rename(columns=str.title)
    end = _write_df(ws, a, r, index=False)
    for i, rec in enumerate(a.itertuples(index=False), start=r + 1):
        ws.cell(row=i, column=2).fill = PatternFill("solid", fgColor=RED if rec.Severity == "High" else AMBER)
    _autowidth(ws, 28, 18)
    ws.column_dimensions["G"].width = 70

    if res.forecast is not None:
        ws = wb.create_sheet("Forecast")
        r = _title(ws, "3-Month Forecast", "Revenue: damped Holt model with 80% band; costs: recent run-rates/ratios")
        d = res.forecast.copy()
        d.index.name = "Line item"
        _write_df(ws, d, r)
        _autowidth(ws)

    ws = wb.create_sheet("Data Quality")
    r = _title(ws, "Data Validation Report")
    for level, items in (("ERROR", res.validation.errors), ("WARNING", res.validation.warnings), ("INFO", res.validation.info)):
        for it in items:
            ws.cell(row=r, column=1, value=level).font = Font(bold=True, color={"ERROR": "C00000", "WARNING": "BF8F00"}.get(level, "375623"))
            ws.cell(row=r, column=2, value=it)
            r += 1
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 12, 120

    wb.properties.title = f"MIS {month_label(m)}"
    wb.properties.creator = "AI Finance Co-Pilot"
    path = Path(path)
    wb.save(path)
    return path
