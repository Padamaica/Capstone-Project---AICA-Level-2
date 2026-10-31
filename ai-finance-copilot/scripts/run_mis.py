"""CLI: generate the monthly MIS pack.

    python scripts/run_mis.py                                # sample data, latest month
    python scripts/run_mis.py --gl my_gl.xlsx --budget budget.csv --month 2026-09
    python scripts/run_mis.py --no-llm                       # rule-based commentary only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot.pipeline import generate_reports, run_analysis  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Finance Co-Pilot: MIS generator")
    ap.add_argument("--gl", default=str(ROOT / "data/sample/gl.csv"))
    ap.add_argument("--budget", default=str(ROOT / "data/sample/budget.csv"))
    ap.add_argument("--mapping", default=None)
    ap.add_argument("--month", default=None, help="YYYY-MM (default: latest)")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()

    res = run_analysis(a.gl, a.budget if a.budget else None, a.mapping, a.month, use_llm=not a.no_llm, user="cli")
    print("\n".join(res.validation.info + res.validation.warnings))
    print(f"\nCommentary source: {res.commentary['source']} {res.commentary.get('note', '')}\n")
    print(res.commentary["text"])
    paths = generate_reports(res, user="cli")
    print("\nReports:", *[f"  {k}: {v}" for k, v in paths.items()], sep="\n")


if __name__ == "__main__":
    main()
