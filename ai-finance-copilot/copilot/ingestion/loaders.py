"""Loaders for General Ledger, Budget and Chart-of-Accounts mapping.

Supported inputs:
    * CSV / Excel (.xlsx/.xls) exports from Tally, Zoho Books, SAP, Busy, QuickBooks, etc.
    * Tally XML Day Book export (Gateway of Tally > Display > Day Book > Export > XML)

Column names are normalised via aliases so most ERP exports work without editing.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import BinaryIO, Union

import pandas as pd

FileLike = Union[str, Path, BinaryIO, io.BytesIO]

GL_ALIASES = {
    "date": ["date", "voucher date", "posting date", "txn date", "transaction date", "vch date"],
    "voucher_no": ["voucher_no", "voucher no", "voucher number", "vch no", "vch no.", "document no", "doc no", "entry no"],
    "voucher_type": ["voucher_type", "voucher type", "vch type", "document type", "doc type"],
    "account": ["account", "ledger", "ledger name", "gl account", "account name", "particulars", "gl name"],
    "party": ["party", "party name", "customer/vendor", "counterparty", "sub ledger", "name"],
    "debit": ["debit", "dr", "debit amount", "dr amount"],
    "credit": ["credit", "cr", "credit amount", "cr amount"],
    "amount": ["amount", "value"],
    "drcr": ["dr/cr", "drcr", "type", "dr_cr"],
    "cost_center": ["cost_center", "cost center", "cost centre", "department", "profit center"],
    "narration": ["narration", "description", "remarks", "memo", "text"],
}
GL_REQUIRED = ["date", "voucher_no", "account", "debit", "credit"]


def _read_tabular(src: FileLike, filename: str | None = None) -> pd.DataFrame:
    name = (filename or (str(src) if isinstance(src, (str, Path)) else getattr(src, "name", ""))).lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(src)
    if name.endswith(".xml"):
        return parse_tally_daybook_xml(src)
    return pd.read_csv(src)


def _normalise_columns(df: pd.DataFrame, aliases: dict[str, list[str]]) -> pd.DataFrame:
    lookup = {a: canon for canon, alist in aliases.items() for a in alist}
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in lookup and lookup[key] not in rename.values():
            rename[col] = lookup[key]
    return df.rename(columns=rename)


def load_gl(src: FileLike, filename: str | None = None) -> pd.DataFrame:
    df = _read_tabular(src, filename)
    df = _normalise_columns(df, GL_ALIASES)

    # Single "amount" column + Dr/Cr indicator -> debit/credit
    if "debit" not in df.columns and "amount" in df.columns:
        amt = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        if "drcr" in df.columns:
            is_dr = df["drcr"].astype(str).str.strip().str.lower().str.startswith("d")
            df["debit"] = amt.where(is_dr, 0.0).abs()
            df["credit"] = amt.where(~is_dr, 0.0).abs()
        else:  # signed amounts: +debit / -credit
            df["debit"] = amt.clip(lower=0)
            df["credit"] = (-amt).clip(lower=0)

    missing = [c for c in GL_REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"GL file is missing required columns: {missing}. Found: {list(df.columns)}")

    for col, default in [("voucher_type", ""), ("party", ""), ("cost_center", ""), ("narration", "")]:
        if col not in df.columns:
            df[col] = default

    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=False)
    df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0.0).round(2)
    df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0.0).round(2)
    for c in ["voucher_no", "voucher_type", "account", "party", "cost_center", "narration"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["month"] = df["date"].dt.to_period("M").astype(str)
    cols = ["date", "month", "voucher_no", "voucher_type", "account", "party", "debit", "credit", "cost_center", "narration"]
    return df[cols].reset_index(drop=True)


def load_budget(src: FileLike, filename: str | None = None) -> pd.DataFrame:
    """Budget format: month (YYYY-MM), category, amount (positive numbers)."""
    df = _read_tabular(src, filename)
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = {"month", "category", "amount"} - set(df.columns)
    if missing:
        raise ValueError(f"Budget file missing columns: {sorted(missing)}")
    df["month"] = pd.to_datetime(df["month"].astype(str)).dt.to_period("M").astype(str)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["category"] = df["category"].astype(str).str.strip()
    return df[["month", "category", "amount"]]


def load_coa_mapping(src: FileLike, filename: str | None = None) -> pd.DataFrame:
    """Mapping format: account, category, statement (PL/BS)."""
    df = _read_tabular(src, filename)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df["account"] = df["account"].astype(str).str.strip()
    df["category"] = df["category"].astype(str).str.strip()
    df["statement"] = df["statement"].astype(str).str.strip().str.upper()
    return df[["account", "category", "statement"]]


def parse_tally_daybook_xml(src: FileLike) -> pd.DataFrame:
    """Parse a Tally Day Book XML export into GL rows.

    Tally convention: ISDEEMEDPOSITIVE=Yes and negative AMOUNT => Debit; positive AMOUNT => Credit.
    """
    tree = ET.parse(src)
    out = []
    for v in tree.getroot().iter("VOUCHER"):
        d = (v.findtext("DATE") or "").strip()
        vno = (v.findtext("VOUCHERNUMBER") or "").strip()
        vtype = v.get("VCHTYPE") or (v.findtext("VOUCHERTYPENAME") or "")
        party = (v.findtext("PARTYLEDGERNAME") or "").strip()
        narr = (v.findtext("NARRATION") or "").strip()
        entries = list(v.iter("ALLLEDGERENTRIES.LIST")) + list(v.iter("LEDGERENTRIES.LIST"))
        for e in entries:
            ledger = (e.findtext("LEDGERNAME") or "").strip()
            try:
                amt = float((e.findtext("AMOUNT") or "0").replace(",", ""))
            except ValueError:
                amt = 0.0
            out.append(dict(date=pd.to_datetime(d, format="%Y%m%d", errors="coerce"), voucher_no=vno, voucher_type=vtype,
                            account=ledger, party=party if ledger == party else "",
                            debit=abs(amt) if amt < 0 else 0.0, credit=amt if amt > 0 else 0.0, narration=narr))
    return pd.DataFrame(out)
