"""Data-quality checks run before any analysis. Bad input data gives a bad MIS, so fail loudly."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "info": self.info}


def validate_gl(gl: pd.DataFrame, mapping: pd.DataFrame) -> ValidationReport:
    r = ValidationReport()

    bad_dates = int(gl["date"].isna().sum())
    if bad_dates:
        r.errors.append(f"{bad_dates} rows have invalid/missing dates.")

    total_dr, total_cr = gl["debit"].sum(), gl["credit"].sum()
    if abs(total_dr - total_cr) > 1:
        r.errors.append(f"Trial balance does not tally: Dr {total_dr:,.2f} vs Cr {total_cr:,.2f} (diff {total_dr - total_cr:,.2f}).")
    else:
        r.info.append(f"Trial balance tallies: Dr = Cr = {total_dr:,.2f}.")

    vb = gl.groupby("voucher_no")[["debit", "credit"]].sum()
    unbalanced = vb[(vb["debit"] - vb["credit"]).abs() > 0.5]
    if len(unbalanced):
        r.errors.append(f"{len(unbalanced)} vouchers are unbalanced, e.g. {list(unbalanced.index[:5])}.")

    unmapped = sorted(set(gl["account"]) - set(mapping["account"]))
    if unmapped:
        r.errors.append(f"{len(unmapped)} ledger accounts are not in the chart-of-accounts mapping: {unmapped[:10]}")

    both = gl[(gl["debit"] > 0) & (gl["credit"] > 0)]
    if len(both):
        r.warnings.append(f"{len(both)} rows have both debit and credit populated.")

    neg = gl[(gl["debit"] < 0) | (gl["credit"] < 0)]
    if len(neg):
        r.warnings.append(f"{len(neg)} rows have negative amounts.")

    dups = gl.duplicated(subset=["date", "voucher_no", "account", "party", "debit", "credit"], keep=False)
    if dups.any():
        r.warnings.append(f"{int(dups.sum())} rows look like exact duplicates (same voucher/account/amount).")

    if gl["date"].notna().any():
        months = pd.period_range(gl["date"].min(), gl["date"].max(), freq="M").astype(str)
        missing = sorted(set(months) - set(gl["month"]))
        if missing:
            r.warnings.append(f"No entries for months: {missing}")
        r.info.append(f"Period covered: {gl['date'].min():%d-%b-%Y} to {gl['date'].max():%d-%b-%Y} ({len(months)} months).")
    r.info.append(f"{len(gl):,} rows, {gl['voucher_no'].nunique():,} vouchers, {gl['account'].nunique()} ledgers.")
    return r
