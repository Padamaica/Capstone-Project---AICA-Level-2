"""Scheduled monthly MIS run + email to management via your INTERNAL SMTP server.

Schedule it with:
  Linux cron (3rd of each month, 7 AM):   0 7 3 * *  cd /opt/ai-finance-copilot && python scripts/monthly_job.py --gl /data/exports/gl.csv
  Windows Task Scheduler:                 python C:\\copilot\\scripts\\monthly_job.py --gl C:\\exports\\gl.xlsx

By default it reports on the previous month. The email is skipped if SMTP_HOST is not set.
"""
from __future__ import annotations

import argparse
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot.config import settings  # noqa: E402
from copilot.localisation import assert_local_endpoint  # noqa: E402
from copilot.pipeline import generate_reports, run_analysis  # noqa: E402
from copilot.storage import audit  # noqa: E402
from copilot.utils import month_label  # noqa: E402


def send_email(paths: dict, res) -> None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        print("SMTP_HOST not set; skipping email.")
        return
    assert_local_endpoint(f"smtp://{host}")  # internal mail relay only (or allow-list an in-country relay)
    msg = EmailMessage()
    msg["Subject"] = f"MIS Pack: {settings.company_name}: {month_label(res.month)}"
    msg["From"] = os.environ.get("MIS_EMAIL_FROM", "mis@localhost")
    msg["To"] = os.environ.get("MIS_EMAIL_TO", "")
    msg.set_content(f"Dear Team,\n\nPlease find attached the MIS pack for {month_label(res.month)}.\n\n"
                    f"{res.commentary.get('text', '')}\n\nRegards,\nAI Finance Co-Pilot")
    for p in paths.values():
        sub = "pdf" if p.suffix == ".pdf" else "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        msg.add_attachment(p.read_bytes(), maintype="application", subtype=sub, filename=p.name)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        s.send_message(msg)
    audit("mis_emailed", "scheduler", to=msg["To"], month=res.month)
    print(f"Emailed to {msg['To']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gl", default=str(ROOT / "data/sample/gl.csv"))
    ap.add_argument("--budget", default=str(ROOT / "data/sample/budget.csv"))
    ap.add_argument("--month", default=None, help="default: previous calendar month (if present in data)")
    a = ap.parse_args()
    month = a.month or str(pd.Timestamp.today().to_period("M") - 1)
    try:
        res = run_analysis(a.gl, a.budget, None, month, user="scheduler")
    except ValueError as e:
        if "not in data" in str(e) and not a.month:
            res = run_analysis(a.gl, a.budget, None, None, user="scheduler")  # fall back to latest month in file
        else:
            raise
    paths = generate_reports(res, user="scheduler")
    print(f"MIS for {res.month}: {[str(p) for p in paths.values()]}")
    send_email(paths, res)


if __name__ == "__main__":
    main()
