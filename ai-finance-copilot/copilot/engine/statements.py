"""Deterministic financial statements: P&L, Balance Sheet, Cash Flow (indirect).

Golden rule: every number in the MIS is computed here in Python. The LLM only explains.
"""
from __future__ import annotations

import pandas as pd

INCOME_CATS = ["Revenue", "Other Income"]
EXPENSE_CATS = ["COGS", "Employee Cost", "Admin Expenses", "Marketing Expenses", "Depreciation", "Finance Cost", "Tax"]
ASSET_CATS = ["Fixed Assets", "Receivables", "Inventory", "Other Current Assets", "Cash & Bank"]
LIAB_CATS = ["Payables", "Statutory Dues", "Other Current Liabilities", "Borrowings"]
EQUITY_CATS = ["Share Capital"]

PL_ORDER = [
    "Revenue", "COGS", "Gross Profit", "Employee Cost", "Admin Expenses", "Marketing Expenses",
    "EBITDA", "Depreciation", "EBIT", "Finance Cost", "Other Income", "PBT", "Tax", "PAT",
]


def enrich(gl: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """Attach category/statement to each GL line. Unmapped accounts are tagged 'Unmapped'."""
    out = gl.merge(mapping, on="account", how="left")
    out["category"] = out["category"].fillna("Unmapped")
    out["statement"] = out["statement"].fillna("NA")
    out["net_dr"] = out["debit"] - out["credit"]
    return out


def opening_mask(egl: pd.DataFrame) -> pd.Series:
    return egl["narration"].str.contains("opening", case=False, na=False)


def pnl_monthly(egl: pd.DataFrame) -> pd.DataFrame:
    """Rows = P&L line items, columns = months (YYYY-MM)."""
    pl = egl[egl["statement"] == "PL"]
    piv = pl.pivot_table(index="category", columns="month", values="net_dr", aggfunc="sum", fill_value=0.0)
    months = sorted(egl["month"].dropna().unique())
    piv = piv.reindex(columns=months, fill_value=0.0)
    get = lambda c: piv.loc[c] if c in piv.index else pd.Series(0.0, index=months)

    r = {}
    r["Revenue"] = -get("Revenue")
    r["Other Income"] = -get("Other Income")
    for c in EXPENSE_CATS:
        r[c] = get(c)
    r["Gross Profit"] = r["Revenue"] - r["COGS"]
    r["EBITDA"] = r["Gross Profit"] - r["Employee Cost"] - r["Admin Expenses"] - r["Marketing Expenses"]
    r["EBIT"] = r["EBITDA"] - r["Depreciation"]
    r["PBT"] = r["EBIT"] - r["Finance Cost"] + r["Other Income"]
    r["PAT"] = r["PBT"] - r["Tax"]
    return pd.DataFrame(r).T.reindex(PL_ORDER).round(2)


def balance_sheet_monthly(egl: pd.DataFrame, pnl: pd.DataFrame | None = None) -> pd.DataFrame:
    """Closing balances at each month end. Retained earnings = cumulative PAT."""
    pnl = pnl if pnl is not None else pnl_monthly(egl)
    months = list(pnl.columns)
    bs = egl[egl["statement"] == "BS"]
    piv = bs.pivot_table(index="category", columns="month", values="net_dr", aggfunc="sum", fill_value=0.0)
    piv = piv.reindex(columns=months, fill_value=0.0).cumsum(axis=1)

    rows = {}
    for c in ASSET_CATS:
        if c in piv.index:
            rows[c] = piv.loc[c]
    rows["Total Assets"] = sum(rows.values())
    liab = {c: -piv.loc[c] for c in LIAB_CATS if c in piv.index}
    rows.update(liab)
    rows["Total Liabilities"] = sum(liab.values()) if liab else 0.0
    eq = {c: -piv.loc[c] for c in EQUITY_CATS if c in piv.index}
    eq["Retained Earnings"] = pnl.loc["PAT"].cumsum()
    rows.update(eq)
    rows["Total Equity"] = sum(eq.values())
    rows["Total Liabilities & Equity"] = rows["Total Liabilities"] + rows["Total Equity"]
    rows["Check (should be 0)"] = rows["Total Assets"] - rows["Total Liabilities & Equity"]
    return pd.DataFrame(rows).T.round(2)


def cash_flow_monthly(egl: pd.DataFrame, pnl: pd.DataFrame | None = None, bs: pd.DataFrame | None = None) -> pd.DataFrame:
    """Indirect-method cash flow. Opening-balance vouchers are treated as the starting position, not flows."""
    pnl = pnl if pnl is not None else pnl_monthly(egl)
    bs = bs if bs is not None else balance_sheet_monthly(egl, pnl)
    months = list(pnl.columns)

    op = egl[opening_mask(egl) & (egl["statement"] == "BS")].groupby("category")["net_dr"].sum()
    opening = pd.Series(0.0, index=bs.index)
    for c, v in op.items():
        if c in opening.index:
            opening[c] = v if c in ASSET_CATS else -v
    prev = pd.concat([opening.rename("open"), bs[months[:-1]]], axis=1)
    prev.columns = months
    delta = bs[months] - prev
    g = lambda c: delta.loc[c] if c in delta.index else pd.Series(0.0, index=months)

    cf = {}
    cf["PAT"] = pnl.loc["PAT"]
    cf["Add: Depreciation"] = pnl.loc["Depreciation"]
    cf["(Inc)/Dec in Receivables"] = -g("Receivables")
    cf["(Inc)/Dec in Inventory"] = -g("Inventory")
    cf["(Inc)/Dec in Other Current Assets"] = -g("Other Current Assets")
    cf["Inc/(Dec) in Payables"] = g("Payables")
    cf["Inc/(Dec) in Statutory Dues"] = g("Statutory Dues")
    cf["Inc/(Dec) in Other Current Liabilities"] = g("Other Current Liabilities")
    cf["Cash from Operations (CFO)"] = sum(cf.values())
    cf["Capex (CFI)"] = -(g("Fixed Assets") + pnl.loc["Depreciation"])
    cf["Net Borrowings"] = g("Borrowings")
    cf["Equity Raised"] = g("Share Capital")
    cf["Cash from Financing (CFF)"] = cf["Net Borrowings"] + cf["Equity Raised"]
    cf["Free Cash Flow (CFO + CFI)"] = cf["Cash from Operations (CFO)"] + cf["Capex (CFI)"]
    cf["Net Change in Cash"] = cf["Cash from Operations (CFO)"] + cf["Capex (CFI)"] + cf["Cash from Financing (CFF)"]
    cf["Closing Cash"] = bs.loc["Cash & Bank"] if "Cash & Bank" in bs.index else 0.0
    cf["Check vs Bank Movement (should be 0)"] = cf["Net Change in Cash"] - g("Cash & Bank")
    df = pd.DataFrame(cf).T.round(2)
    return df.drop(index=[r for r in ["(Inc)/Dec in Inventory", "Inc/(Dec) in Other Current Liabilities"]
                          if (df.loc[r].abs() < 0.01).all()])


def fy_label(month: str, fy_start_month: int = 4) -> str:
    p = pd.Period(month, freq="M")
    start = p.year if p.month >= fy_start_month else p.year - 1
    return f"FY{str(start)[2:]}-{str(start + 1)[2:]}"


def ytd_columns(months: list[str], month: str, fy_start_month: int = 4) -> list[str]:
    fy = fy_label(month, fy_start_month)
    return [m for m in months if fy_label(m, fy_start_month) == fy and m <= month]
