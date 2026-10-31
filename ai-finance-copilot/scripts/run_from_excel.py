"""Month-end in one step: Excel in -> complete MIS out.

    python scripts/run_from_excel.py                      # newest .xlsx in input/
    python scripts/run_from_excel.py input/MIS_Input_Oct-2026.xlsx --month 2026-10

Output folder: output/<YYYY-MM>/  ->  MIS_<month>.xlsx, MIS_<month>.pdf, AI_Output_<month>.md, Run_Summary.txt
If the data fails validation, output/VALIDATION_ERRORS.txt explains exactly what to fix.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot.ai import ask  # noqa: E402
from copilot.ai.llm import get_llm  # noqa: E402
from copilot.config import settings  # noqa: E402
from copilot.ingestion.workbook import latest_input_file, split_input_workbook  # noqa: E402
from copilot.pipeline import generate_reports, run_analysis  # noqa: E402

QUESTIONS = [
    "What was the revenue trend in the last 6 months?",
    "Which customers have the highest overdue receivables?",
    "What were the top 5 expenses in the latest month?",
    "How has closing cash moved over the last 6 months?",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Finance Co-Pilot: Excel in -> MIS out")
    ap.add_argument("file", nargs="?", help="input workbook (default: newest .xlsx in input/)")
    ap.add_argument("--month", default=None, help="YYYY-MM (default: latest month in the data)")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()

    src = Path(a.file) if a.file else latest_input_file(ROOT / "input")
    t0 = time.time()
    print(f"[1/5] Reading workbook: {src.name}")
    parts = split_input_workbook(src)
    print(f"      Sheets used: {parts.sheets_found}")

    llm = get_llm()
    status = "not configured" if llm is None else ("ONLINE" if llm.health() else "OFFLINE (rule-based fallback)")
    use_llm = not a.no_llm
    print(f"[2/5] Validating + computing (LLM {settings.llm_model}: {status if use_llm else 'off'})")
    try:
        res = run_analysis(parts.gl, parts.budget, parts.mapping, a.month, gl_name="gl.csv",
                           budget_name="budget.csv", use_llm=use_llm, user="excel_run")
    except ValueError as e:
        err = ROOT / "output" / "VALIDATION_ERRORS.txt"
        err.parent.mkdir(parents=True, exist_ok=True)
        err.write_text(f"Input: {src.name}\nRun: {datetime.now():%d-%b-%Y %H:%M}\n\n{e}\n\n"
                       "Fix the workbook (usually: add missing ledgers to the Mapping sheet) and run again.\n",
                       encoding="utf-8")
        print(f"\nSTOPPED - data validation failed. See {err}\n{e}")
        return 1

    out_dir = ROOT / "output" / res.month
    print(f"[3/5] Building Excel + PDF packs -> {out_dir}")
    paths = generate_reports(res, out_dir=out_dir, user="excel_run")

    print("[4/5] Ask-your-data questions")
    qa = []
    for q in QUESTIONS:
        r = ask(q, res.party_names, use_llm=use_llm)
        qa += ["", f"### Q: {q}", f"*{r['source']} | {r.get('note', '')}*", "", r["answer"]]

    md = out_dir / f"AI_Output_{res.month}.md"
    md.write_text("\n".join([f"# AI output: {res.month}  ({src.name})", "",
                             f"Commentary source: {res.commentary['source']} {res.commentary.get('note', '')}", "",
                             res.commentary["text"], "", "## Ask your data", *qa]), encoding="utf-8")

    summary = [f"AI Finance Co-Pilot - run summary", f"Input file : {src.name}", f"Month      : {res.month}",
               f"Run at     : {datetime.now():%d-%b-%Y %H:%M}", f"Time taken : {time.time() - t0:.0f} sec",
               f"AI model   : {settings.llm_model} ({status})", "", "Data checks:",
               *[f"  - {x}" for x in res.validation.info + res.validation.warnings],
               f"  - Anomalies flagged: {len(res.anomalies)}", "", "Files:",
               *[f"  - {p.name}" for p in [paths['excel'], paths['pdf'], md]]]
    (out_dir / "Run_Summary.txt").write_text("\n".join(summary), encoding="utf-8")
    print("[5/5] Done in %.0f sec\n" % (time.time() - t0))
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
