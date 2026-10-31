"""Ratios, budget-vs-actual variance and AR/AP ageing."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .statements import ytd_columns

FAVOURABLE_IF_HIGHER = {"Revenue", "Other Income", "Gross Profit", "EBITDA", "EBIT", "PBT", "PAT"}


def _safe_div(a, b):
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    return (a / b.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def ratios_monthly(pnl: pd.DataFrame, bs: pd.DataFrame) -> pd.DataFrame:
    months = list(pnl.columns)
    days = pd.Series([pd.Period(m, freq="M").days_in_month for m in months], index=months, dtype=float)
    rev, cogs = pnl.loc["Revenue"], pnl.loc["COGS"]
    g = lambda c: bs.loc[c] if c in bs.index else pd.Series(0.0, index=months)
    ca = g("Receivables") + g("Inventory") + g("Other Current Assets") + g("Cash & Bank")
    cl = g("Payables") + g("Statutory Dues") + g("Other Current Liabilities")
    r = {
        "Revenue Growth MoM %": rev.pct_change() * 100,
        "Gross Margin %": _safe_div(pnl.loc["Gross Profit"], rev) * 100,
        "EBITDA Margin %": _safe_div(pnl.loc["EBITDA"], rev) * 100,
        "PAT Margin %": _safe_div(pnl.loc["PAT"], rev) * 100,
        "Employee Cost % Revenue": _safe_div(pnl.loc["Employee Cost"], rev) * 100,
        "Current Ratio (x)": _safe_div(ca, cl),
        "Debt / Equity (x)": _safe_div(g("Borrowings"), bs.loc["Total Equity"]),
        "Interest Coverage (x)": _safe_div(pnl.loc["EBIT"], pnl.loc["Finance Cost"]),
        "DSO (days)": _safe_div(g("Receivables"), rev * 1.18) * days,  # receivables carry GST
        "DPO (days)": _safe_div(g("Payables"), cogs * 1.18) * days,
        "Working Capital": ca - cl,
        "Cash & Bank": g("Cash & Bank"),
    }
    return pd.DataFrame(r).T.round(2)


def budget_vs_actual(pnl: pd.DataFrame, budget: pd.DataFrame, month: str, ytd: bool = False,
                     fy_start_month: int = 4, threshold_pct: float = 10.0) -> pd.DataFrame:
    cols = ytd_columns(list(pnl.columns), month, fy_start_month) if ytd else [month]
    actual = pnl[cols].sum(axis=1)
    bud = budget[budget["month"].isin(cols)].groupby("category")["amount"].sum()

    # derive budget subtotals so the table mirrors the P&L
    b = lambda c: float(bud.get(c, 0.0))
    derived = {
        "Gross Profit": b("Revenue") - b("COGS"),
        "EBITDA": b("Revenue") - b("COGS") - b("Employee Cost") - b("Admin Expenses") - b("Marketing Expenses"),
    }
    derived["EBIT"] = derived["EBITDA"] - b("Depreciation")
    derived["PBT"] = derived["EBIT"] - b("Finance Cost") + b("Other Income")
    rows = []
    for line in pnl.index:
        if line in ("Tax", "PAT"):
            continue
        bv = derived.get(line, b(line))
        av = float(actual.get(line, 0.0))
        var = av - bv
        var_pct = (var / abs(bv) * 100) if bv else np.nan
        fav = var >= 0 if line in FAVOURABLE_IF_HIGHER else var <= 0
        rows.append(dict(line_item=line, budget=round(bv, 2), actual=round(av, 2), variance=round(var, 2),
                         variance_pct=round(var_pct, 2) if pd.notna(var_pct) else np.nan,
                         status="Favourable" if fav else "Adverse",
                         flag=bool(pd.notna(var_pct) and abs(var_pct) >= threshold_pct)))
    return pd.DataFrame(rows)


BUCKETS = [(0, 30, "0-30"), (31, 60, "31-60"), (61, 90, "61-90"), (91, 180, "91-180"), (181, 10**6, "180+")]


def _bucket(days: int) -> str:
    for lo, hi, name in BUCKETS:
        if lo <= days <= hi:
            return name
    return "180+"


def ageing(egl: pd.DataFrame, as_of: str | pd.Timestamp, kind: str = "AR") -> tuple[pd.DataFrame, pd.DataFrame]:
    """FIFO ageing of open items for Receivables (AR) or Payables (AP).

    Returns (detail of open invoices, summary pivot party x bucket).
    """
    as_of = pd.Timestamp(as_of)
    cat = "Receivables" if kind == "AR" else "Payables"
    ctl = egl[(egl["category"] == cat) & (egl["date"] <= as_of) & (egl["party"] != "")]
    detail = []
    for party, g in ctl.groupby("party"):
        g = g.sort_values("date")
        inv_col, pay_col = ("debit", "credit") if kind == "AR" else ("credit", "debit")
        invoices = g[g[inv_col] > 0][["date", "voucher_no", inv_col]].values.tolist()
        paid = float(g[pay_col].sum())
        for d, vno, amt in invoices:
            alloc = min(paid, amt)
            paid -= alloc
            open_amt = round(amt - alloc, 2)
            if open_amt > 0.5:
                age = (as_of - pd.Timestamp(d)).days
                detail.append(dict(party=party, invoice_date=pd.Timestamp(d).date(), voucher_no=vno,
                                   open_amount=open_amt, age_days=age, bucket=_bucket(age)))
    det = pd.DataFrame(detail, columns=["party", "invoice_date", "voucher_no", "open_amount", "age_days", "bucket"])
    names = [b[2] for b in BUCKETS]
    if det.empty:
        return det, pd.DataFrame(columns=["party", *names, "Total"])
    summ = det.pivot_table(index="party", columns="bucket", values="open_amount", aggfunc="sum", fill_value=0.0)
    summ = summ.reindex(columns=names, fill_value=0.0)
    summ["Total"] = summ.sum(axis=1)
    summ = summ.sort_values("Total", ascending=False)
    summ.loc["TOTAL"] = summ.sum()
    return det.sort_values(["age_days"], ascending=False), summ.round(2).reset_index()
