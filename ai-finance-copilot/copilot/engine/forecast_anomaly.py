"""Forecasting (damped Holt) and anomaly detection, with numpy/pandas only (no heavy ML deps).

Swap in statsmodels / Prophet / scikit-learn IsolationForest later without changing callers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------- forecasting
def holt_damped(y: np.ndarray, horizon: int, alpha: float, beta: float, phi: float) -> tuple[np.ndarray, np.ndarray]:
    level, trend = y[0], (y[1] - y[0]) if len(y) > 1 else 0.0
    fitted = []
    for t in range(len(y)):
        fitted.append(level + phi * trend)
        new_level = alpha * y[t] + (1 - alpha) * (level + phi * trend)
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    fc = np.array([level + sum(phi ** k for k in range(1, h + 1)) * trend for h in range(1, horizon + 1)])
    return np.array(fitted), fc


def forecast_series(series: pd.Series, horizon: int = 3) -> pd.DataFrame:
    """Grid-search a damped Holt model on in-sample one-step error; return forecast with ~80% band."""
    y = series.astype(float).values
    if len(y) < 4:
        raise ValueError("Need at least 4 periods to forecast.")
    best = None
    for a in (0.2, 0.4, 0.6, 0.8):
        for b in (0.05, 0.1, 0.2, 0.3):
            for phi in (0.8, 0.9, 0.98):
                fitted, fc = holt_damped(y, horizon, a, b, phi)
                sse = float(np.sum((y[1:] - fitted[1:]) ** 2))
                if best is None or sse < best[0]:
                    best = (sse, fc, fitted, (a, b, phi))
    sse, fc, fitted, params = best
    sigma = float(np.std(y[1:] - fitted[1:], ddof=1))
    last = pd.Period(series.index[-1], freq="M")
    idx = [str(last + h) for h in range(1, horizon + 1)]
    band = 1.28 * sigma * np.sqrt(np.arange(1, horizon + 1))
    return pd.DataFrame({"forecast": fc.round(0), "low_80": (fc - band).round(0), "high_80": (fc + band).round(0)}, index=idx).assign(
        model=f"Damped Holt a={params[0]} b={params[1]} phi={params[2]}")


def forecast_pnl(pnl: pd.DataFrame, horizon: int = 3) -> pd.DataFrame:
    """Revenue via Holt; costs via recent ratios/run-rates; returns projected P&L lines."""
    rev = forecast_series(pnl.loc["Revenue"], horizon)
    last6 = pnl.iloc[:, -6:]
    cogs_ratio = last6.loc["COGS"].sum() / last6.loc["Revenue"].sum()
    fixed = {c: pnl.loc[c].iloc[-3:].mean() for c in ["Employee Cost", "Admin Expenses", "Marketing Expenses",
                                                     "Depreciation", "Finance Cost", "Other Income"]}
    out = pd.DataFrame(index=rev.index)
    out["Revenue"] = rev["forecast"]
    out["COGS"] = out["Revenue"] * cogs_ratio
    out["Gross Profit"] = out["Revenue"] - out["COGS"]
    for c, v in fixed.items():
        out[c] = v
    out["EBITDA"] = out["Gross Profit"] - out["Employee Cost"] - out["Admin Expenses"] - out["Marketing Expenses"]
    out["PBT"] = out["EBITDA"] - out["Depreciation"] - out["Finance Cost"] + out["Other Income"]
    out["Revenue Low (80%)"] = rev["low_80"]
    out["Revenue High (80%)"] = rev["high_80"]
    return out.round(0).T


# ----------------------------------------------------------------------------- anomalies
def _robust_z(x: pd.Series) -> pd.Series:
    med = x.median()
    mad = (x - med).abs().median()
    if mad == 0:
        return pd.Series(np.where((x - med).abs() > 0.5 * abs(med) + 1e-9, 99.0, 0.0), index=x.index)
    return 0.6745 * (x - med) / mad


def detect_duplicate_payments(egl: pd.DataFrame, window_days: int = 7) -> pd.DataFrame:
    bank_vouchers = set(egl[(egl["category"] == "Cash & Bank") & (egl["credit"] > 0)]["voucher_no"])
    pay = egl[egl["voucher_no"].isin(bank_vouchers) & (egl["category"] != "Cash & Bank") & (egl["debit"] > 0) & (egl["party"] != "")]
    pay = pay.sort_values("date")
    out = []
    for (party, amt), g in pay.groupby(["party", "debit"]):
        if len(g) < 2:
            continue
        g = g.sort_values("date").reset_index(drop=True)
        recurring = g["month"].nunique() >= 3  # e.g. rent/EMI: only a same-month repeat is suspicious
        for i in range(1, len(g)):
            gap = (g.loc[i, "date"] - g.loc[i - 1, "date"]).days
            same_month = g.loc[i, "month"] == g.loc[i - 1, "month"]
            if gap <= window_days and g.loc[i, "voucher_no"] != g.loc[i - 1, "voucher_no"] and (same_month or not recurring):
                out.append(dict(type="Possible duplicate payment", severity="High", date=g.loc[i, "date"].date(),
                                account=g.loc[i, "account"], party=party, amount=amt,
                                detail=f"Same amount paid {gap} day(s) apart: {g.loc[i - 1, 'voucher_no']} and {g.loc[i, 'voucher_no']}"))
    return pd.DataFrame(out)


def detect_expense_spikes(egl: pd.DataFrame, z_threshold: float = 3.0, min_pct: float = 50.0) -> pd.DataFrame:
    exp = egl[(egl["statement"] == "PL") & ~egl["category"].isin(["Revenue", "Other Income", "Tax"])]
    piv = exp.pivot_table(index="account", columns="month", values="net_dr", aggfunc="sum", fill_value=0.0)
    out = []
    for acc, row in piv.iterrows():
        if (row != 0).sum() < 6:
            continue
        z = _robust_z(row)
        med = row.median()
        for m, val in row.items():
            pct = (val - med) / abs(med) * 100 if med else 0
            if z[m] >= z_threshold and pct >= min_pct:
                out.append(dict(type="Expense spike", severity="High" if pct >= 200 else "Medium", date=m, account=acc, party="",
                                amount=round(val, 2), detail=f"{pct:,.0f}% above the monthly median of {med:,.0f}"))
    return pd.DataFrame(out)


def detect_large_transactions(egl: pd.DataFrame, multiple: float = 5.0) -> pd.DataFrame:
    exp = egl[(egl["statement"] == "PL") & (egl["debit"] > 0) & ~egl["category"].isin(["Tax", "COGS"])]
    out = []
    for acc, g in exp.groupby("account"):
        if len(g) < 10:
            continue
        med = g["debit"].median()
        for _, r in g[g["debit"] > multiple * med].iterrows():
            out.append(dict(type="Unusually large entry", severity="Medium", date=r["date"].date(), account=acc, party=r["party"],
                            amount=r["debit"], detail=f"{r['debit'] / med:,.1f}x the typical entry ({r['voucher_no']})"))
    return pd.DataFrame(out)


def detect_anomalies(egl: pd.DataFrame, z_threshold: float = 3.0, window_days: int = 7) -> pd.DataFrame:
    parts = [detect_duplicate_payments(egl, window_days), detect_expense_spikes(egl, z_threshold), detect_large_transactions(egl)]
    parts = [p for p in parts if not p.empty]
    cols = ["type", "severity", "date", "account", "party", "amount", "detail"]
    if not parts:
        return pd.DataFrame(columns=cols)
    df = pd.concat(parts, ignore_index=True)[cols]
    df["_s"] = df["severity"].map({"High": 0, "Medium": 1, "Low": 2})
    return df.sort_values(["_s", "amount"], ascending=[True, False]).drop(columns="_s").reset_index(drop=True)
