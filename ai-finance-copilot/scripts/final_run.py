"""Full run with the local Ollama LLM: MIS pack + AI commentary + 'Ask your data' Q&A.

    python scripts/final_run.py
Writes output/MIS_<month>.xlsx, output/MIS_<month>.pdf and output/AI_Output_<month>.md
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot.ai import ask  # noqa: E402
from copilot.ai.llm import get_llm  # noqa: E402
from copilot.config import settings  # noqa: E402
from copilot.pipeline import generate_reports, run_analysis  # noqa: E402

QUESTIONS = [
    "What was the revenue trend in the last 6 months?",
    "Which customers have the highest overdue receivables?",
    "What were the top 5 expenses in the latest month?",
    "How has closing cash moved over the last 6 months?",
    "What was depreciation in each of the last 3 months?",
]


def main() -> None:
    llm = get_llm()
    status = "not configured"
    if llm is not None:
        status = "ONLINE" if llm.health() else "OFFLINE / model not pulled"
    print(f"Python {sys.version.split()[0]} | LLM: {settings.llm_provider} {settings.llm_model} -> {status}")

    t0 = time.time()
    res = run_analysis(ROOT / "data/sample/gl.csv", ROOT / "data/sample/budget.csv", use_llm=True, user="final_run")
    print(f"Analysis + commentary done in {time.time() - t0:.0f}s | source = {res.commentary['source']} "
          f"{res.commentary.get('note', '')}")
    paths = generate_reports(res, user="final_run")

    out = [f"# AI Finance Co-Pilot: AI output for {res.month}", "",
           f"- Python: {sys.version.split()[0]}",
           f"- LLM: {settings.llm_provider} / {settings.llm_model} ({status})",
           f"- Commentary source: {res.commentary['source']} {res.commentary.get('note', '')}",
           f"- Unverified numbers flagged by numeric guard: {res.commentary.get('unverified_numbers', [])}",
           "", "## Validation", *[f"- {x}" for x in res.validation.info + res.validation.warnings],
           "", "## Management commentary", "", res.commentary["text"], "", "## Ask your data (natural language to SQL)"]
    for q in QUESTIONS:
        t = time.time()
        r = ask(q, res.party_names, use_llm=True)
        print(f"Q: {q} -> {r['source']} ({time.time() - t:.0f}s)")
        out += ["", f"### Q: {q}", f"*Source: {r['source']}*  {r.get('note', '')}", "", r["answer"], "",
                "```sql", str(r["sql"]), "```"]
        if len(r["data"]):
            out += ["", "```text", r["data"].head(12).to_string(index=False), "```"]
    md = Path(settings.output_dir) / f"AI_Output_{res.month}.md"
    md.write_text("\n".join(out), encoding="utf-8")
    print("\nReports:", f"  excel: {paths['excel']}", f"  pdf:   {paths['pdf']}", f"  ai:    {md}", sep="\n")
    print("\n" + res.commentary["text"])


if __name__ == "__main__":
    main()
