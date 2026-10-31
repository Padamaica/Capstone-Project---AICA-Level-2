"""Local SQLite storage + audit log. Everything stays on this machine/server.

SQLite keeps the MVP dependency-free. For production, point SQLAlchemy at PostgreSQL in your
in-country region (e.g. AWS RDS ap-south-1 / Azure Database for PostgreSQL Central India).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import settings

SCHEMA_DOC = """
Tables (SQLite):
  gl(date TEXT 'YYYY-MM-DD', month TEXT 'YYYY-MM', voucher_no TEXT, voucher_type TEXT, account TEXT, party TEXT,
     debit REAL, credit REAL, cost_center TEXT, narration TEXT, category TEXT, statement TEXT 'PL'|'BS')
  budget(month TEXT 'YYYY-MM', category TEXT, amount REAL)
  pnl(month TEXT 'YYYY-MM', line_item TEXT, amount REAL)
     line_item in: Revenue, COGS, Gross Profit, Employee Cost, Admin Expenses, Marketing Expenses, EBITDA,
                   Depreciation, EBIT, Finance Cost, Other Income, PBT, Tax, PAT
  balance_sheet(month TEXT, line_item TEXT, amount REAL)  -- closing balances at month end
  ar_ageing(party TEXT, invoice_date TEXT, voucher_no TEXT, open_amount REAL, age_days INTEGER, bucket TEXT)
  ap_ageing(party TEXT, invoice_date TEXT, voucher_no TEXT, open_amount REAL, age_days INTEGER, bucket TEXT)
Notes: expenses in gl have debit>0; revenue has credit>0. Amounts are in INR. Category values for P&L accounts:
  Revenue, Other Income, COGS, Employee Cost, Admin Expenses, Marketing Expenses, Depreciation, Finance Cost, Tax.
"""


def connect(read_only: bool = False, db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or settings.db_path)
    if read_only:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    return sqlite3.connect(path, check_same_thread=False)


def _long(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index.name = "line_item"
    return out.reset_index().melt(id_vars="line_item", var_name="month", value_name="amount")[["month", "line_item", "amount"]]


def save_results(egl: pd.DataFrame, budget: pd.DataFrame | None, pnl: pd.DataFrame, bs: pd.DataFrame,
                 ar: pd.DataFrame | None = None, ap: pd.DataFrame | None = None, db_path: Path | None = None) -> None:
    con = connect(db_path=db_path)
    try:
        g = egl.drop(columns=["net_dr"], errors="ignore").copy()
        g["date"] = g["date"].dt.strftime("%Y-%m-%d")
        g.to_sql("gl", con, if_exists="replace", index=False)
        if budget is not None:
            budget.to_sql("budget", con, if_exists="replace", index=False)
        _long(pnl).to_sql("pnl", con, if_exists="replace", index=False)
        _long(bs).to_sql("balance_sheet", con, if_exists="replace", index=False)
        for name, df in (("ar_ageing", ar), ("ap_ageing", ap)):
            if df is not None:
                d = df.copy()
                d["invoice_date"] = d["invoice_date"].astype(str)
                d.to_sql(name, con, if_exists="replace", index=False)
        con.execute("CREATE INDEX IF NOT EXISTS ix_gl_month ON gl(month)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_gl_account ON gl(account)")
        con.commit()
    finally:
        con.close()


_audit_lock = threading.Lock()


def audit(event: str, user: str = "system", **details) -> None:
    """Append-only JSON-lines audit trail (who did what, when). Keep for compliance (e.g. CERT-In: 180 days)."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "user": user, "event": event, **details}
    line = json.dumps(rec, default=str, ensure_ascii=False)
    with _audit_lock:
        with open(settings.log_dir / "audit.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
