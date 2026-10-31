"""Formatting helpers (Indian numbering: lakh / crore)."""
from __future__ import annotations

import math

import pandas as pd


def indian_number(x: float, decimals: int = 0) -> str:
    """12345678.9 -> '1,23,45,679'"""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    neg = x < 0
    s = f"{abs(x):.{decimals}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    out = whole + (f".{frac}" if frac else "")
    return f"-{out}" if neg else out


def fmt_inr(x: float) -> str:
    """Compact rupee format: ₹1.23 Cr / ₹45.6 L / ₹12,345"""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    a = abs(x)
    sign = "-" if x < 0 else ""
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:.2f} L"
    return f"{sign}₹{indian_number(a)}"


def fmt_pct(x: float, decimals: int = 1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return f"{x:+.{decimals}f}%" if decimals >= 0 else f"{x}%"


def month_label(m: str) -> str:
    return pd.Period(m, freq="M").strftime("%b-%Y")


def fmt_inr_signed(x: float) -> str:
    s = fmt_inr(x)
    return s if s.startswith("-") or s == "-" else "+" + s
