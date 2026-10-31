"""Management commentary: Python builds a 'fact pack', the LLM writes the narrative, and a numeric guard
checks that every number in the narrative came from the fact pack (hallucination control).
If the LLM is offline, a deterministic rule-based commentary is produced instead.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from ..config import settings
from ..engine.statements import fy_label, ytd_columns
from ..utils import fmt_inr, fmt_inr_signed, month_label
from ..localisation import DataLocalisationError
from .llm import LLMUnavailable, get_llm
from .pii import PIIMasker

SYSTEM_PROMPT = """You are a senior FP&A analyst writing the monthly MIS commentary for the CFO and board of an Indian company.
Rules:
- Use ONLY the facts provided in JSON. Never invent, estimate or recalculate numbers.
- Quote numbers exactly as formatted in the facts (₹ L = lakh, ₹ Cr = crore).
- Be concise, specific and professional. Bullet points, no fluff.
- Structure with these markdown headings: ### Headline, ### Performance, ### Budget Variance,
  ### Cash & Working Capital, ### Risks & Anomalies, ### Recommended Actions.
- Recommended actions must follow logically from the facts (max 4 bullets).
"""


def _pct(a: float, b: float) -> float | None:
    return None if not b else (a - b) / abs(b) * 100


def build_fact_pack(res) -> dict:
    m, p, r = res.month, res.pnl, res.ratios
    months = list(p.columns)
    i = months.index(m)
    prev = months[i - 1] if i > 0 else None
    ly = str(pd.Period(m, freq="M") - 12)
    ytd = ytd_columns(months, m, settings.fy_start_month)
    g = lambda line, col: float(p.loc[line, col])
    f: dict = {"company": settings.company_name, "period": month_label(m), "financial_year": fy_label(m, settings.fy_start_month)}

    f["revenue"] = fmt_inr(g("Revenue", m))
    if prev:
        f["revenue_prev_month"] = fmt_inr(g("Revenue", prev))
        f["revenue_mom_pct"] = f"{_pct(g('Revenue', m), g('Revenue', prev)):+.1f}%"
    if ly in months:
        f["revenue_same_month_last_year"] = fmt_inr(g("Revenue", ly))
        f["revenue_yoy_pct"] = f"{_pct(g('Revenue', m), g('Revenue', ly)):+.1f}%"
    gm = float(r.loc["Gross Margin %", m])
    f["gross_margin"] = f"{gm:.1f}%"
    if prev:
        f["gross_margin_change_bps"] = f"{(gm - float(r.loc['Gross Margin %', prev])) * 100:+.0f} bps"
    f["ebitda"] = fmt_inr(g("EBITDA", m))
    f["ebitda_margin"] = f"{float(r.loc['EBITDA Margin %', m]):.1f}%"
    f["pat"] = fmt_inr(g("PAT", m))
    f["pat_margin"] = f"{float(r.loc['PAT Margin %', m]):.1f}%"
    f["ytd_months"] = f"{month_label(ytd[0])} to {month_label(ytd[-1])}"
    f["ytd_revenue"] = fmt_inr(float(p.loc["Revenue", ytd].sum()))
    f["ytd_pat"] = fmt_inr(float(p.loc["PAT", ytd].sum()))

    exp_lines = ["COGS", "Employee Cost", "Admin Expenses", "Marketing Expenses"]
    if prev:
        moves = sorted(((l, g(l, m) - g(l, prev)) for l in exp_lines), key=lambda x: abs(x[1]), reverse=True)
        f["biggest_cost_movements_vs_prev_month"] = [f"{l}: {fmt_inr_signed(d)}" for l, d in moves[:3]]

    if res.bva_month is not None and not res.bva_month.empty:
        bm = res.bva_month
        rev_row = bm[bm.line_item == "Revenue"].iloc[0]
        f["revenue_vs_budget"] = f"{fmt_inr(rev_row.actual)} vs budget {fmt_inr(rev_row.budget)} ({rev_row.variance_pct:+.1f}%)"
        f["flagged_variances_month"] = [f"{x.line_item}: actual {fmt_inr(x.actual)} vs budget {fmt_inr(x.budget)} "
                                        f"({x.variance_pct:+.1f}%, {x.status})" for x in bm[bm.flag].itertuples()]
    if res.bva_ytd is not None and not res.bva_ytd.empty:
        by = res.bva_ytd
        f["flagged_variances_ytd"] = [f"{x.line_item}: {x.variance_pct:+.1f}% ({x.status})" for x in by[by.flag].itertuples()]

    cash = float(r.loc["Cash & Bank", m])
    f["closing_cash"] = fmt_inr(cash)
    if prev:
        f["cash_change_vs_prev_month"] = fmt_inr_signed(cash - float(r.loc["Cash & Bank", prev]))
    f["cash_from_operations_month"] = fmt_inr(float(res.cash_flow.loc["Cash from Operations (CFO)", m]))
    f["dso_days"] = f"{float(r.loc['DSO (days)', m]):.0f} days"
    f["dpo_days"] = f"{float(r.loc['DPO (days)', m]):.0f} days"
    f["current_ratio"] = f"{float(r.loc['Current Ratio (x)', m]):.2f}x"
    f["debt_equity"] = f"{float(r.loc['Debt / Equity (x)', m]):.2f}x"

    if res.ar_detail is not None and not res.ar_detail.empty:
        old = res.ar_detail[res.ar_detail.age_days > 60]
        f["receivables_total"] = fmt_inr(float(res.ar_detail.open_amount.sum()))
        f["receivables_over_60_days"] = fmt_inr(float(old.open_amount.sum()))
        if not old.empty:
            top = old.groupby("party").open_amount.sum().sort_values(ascending=False)
            f["top_overdue_customers"] = [f"{k}: {fmt_inr(v)}" for k, v in top.head(3).items()]

    if res.anomalies is not None and not res.anomalies.empty:
        f["anomalies_count"] = int(len(res.anomalies))
        f["top_anomalies"] = [f"{a.type} | {a.account} | {a.party or '-'} | {fmt_inr(a.amount)} | {a.date} | {a.detail}"
                              for a in res.anomalies.head(5).itertuples()]
    if res.forecast is not None:
        f["revenue_forecast_next_3_months"] = [f"{month_label(c)}: {fmt_inr(float(res.forecast.loc['Revenue', c]))}"
                                               for c in res.forecast.columns]
    return f


def rule_based_commentary(f: dict) -> str:
    L = [f"### Headline",
         f"- {f['period']}: Revenue {f['revenue']} ({f.get('revenue_mom_pct', 'n/a')} MoM), EBITDA {f['ebitda']} "
         f"({f['ebitda_margin']} margin), PAT {f['pat']}.", "", "### Performance",
         f"- Gross margin {f['gross_margin']} ({f.get('gross_margin_change_bps', 'n/a')} vs last month)."]
    if "revenue_yoy_pct" in f:
        L.append(f"- Revenue vs same month last year: {f['revenue_yoy_pct']} ({f['revenue_same_month_last_year']}).")
    L.append(f"- YTD {f['financial_year']} ({f['ytd_months']}): Revenue {f['ytd_revenue']}, PAT {f['ytd_pat']}.")
    for x in f.get("biggest_cost_movements_vs_prev_month", []):
        L.append(f"- Cost movement vs last month: {x}.")
    L += ["", "### Budget Variance"]
    if "revenue_vs_budget" in f:
        L.append(f"- Revenue {f['revenue_vs_budget']}.")
    L += [f"- {x}" for x in f.get("flagged_variances_month", [])] or ["- No line item beyond the variance threshold this month."]
    if f.get("flagged_variances_ytd"):
        L.append(f"- YTD flags: " + "; ".join(f["flagged_variances_ytd"]) + ".")
    L += ["", "### Cash & Working Capital",
          f"- Closing cash {f['closing_cash']} (change {f.get('cash_change_vs_prev_month', 'n/a')}); CFO for the month {f['cash_from_operations_month']}.",
          f"- DSO {f['dso_days']}, DPO {f['dpo_days']}, current ratio {f['current_ratio']}, debt/equity {f['debt_equity']}."]
    if "receivables_over_60_days" in f:
        L.append(f"- Receivables {f['receivables_total']}, of which {f['receivables_over_60_days']} is older than 60 days.")
    L += ["", "### Risks & Anomalies"]
    L += [f"- {a}" for a in f.get("top_anomalies", [])] or ["- No anomalies detected."]
    L += ["", "### Recommended Actions"]
    acts = []
    if f.get("top_anomalies"):
        acts.append("Review and clear flagged anomalies (possible duplicate payments / unusual expenses) before closing books.")
    if f.get("top_overdue_customers"):
        acts.append("Escalate collections with: " + ", ".join(f["top_overdue_customers"]) + ".")
    if any("Adverse" in x for x in f.get("flagged_variances_month", [])):
        acts.append("Investigate adverse budget variances with budget owners and update the rolling forecast.")
    if f.get("revenue_forecast_next_3_months"):
        acts.append("Plan for next quarter using forecast revenue: " + "; ".join(f["revenue_forecast_next_3_months"]) + ".")
    L += [f"- {a}" for a in acts[:4]]
    return "\n".join(L)


_NUM = re.compile(r"\d[\d,]*\.?\d*")


def _nums(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUM.findall(text)}


def numeric_guard(narrative: str, facts: dict) -> list[str]:
    """Return numbers in the narrative that do not appear in the fact pack."""
    allowed = _nums(json.dumps(facts, ensure_ascii=False))
    bad = []
    for n in _nums(narrative):
        try:
            v = float(n)
        except ValueError:
            continue
        if n in allowed or ("." not in n and v <= 31) or ("." not in n and 2000 <= v <= 2100):
            continue
        bad.append(n)
    return sorted(bad)


def generate_commentary(res, use_llm: bool = True) -> dict:
    facts = build_fact_pack(res)
    fallback = {"text": rule_based_commentary(facts), "source": "rules", "unverified_numbers": [], "facts": facts}
    llm = get_llm() if use_llm else None
    if llm is None:
        return fallback
    masker = PIIMasker(res.party_names if settings.mask_pii_before_llm else [])
    masked = json.loads(masker.mask(json.dumps(facts, ensure_ascii=False))) if settings.mask_pii_before_llm else facts
    attempts = int(settings.__dict__.get("llm_commentary_attempts", 2))
    rejected = []
    for attempt in range(1, attempts + 1):  # small local models are non-deterministic: one retry, then fall back
        try:
            text = llm.chat(SYSTEM_PROMPT, "Facts (JSON):\n" + json.dumps(masked, indent=2, ensure_ascii=False)
                            + ("\n\nIMPORTANT: your previous draft used numbers not in the facts "
                               f"({rejected[-1][:6]}). Use ONLY numbers that appear in the facts." if rejected else ""))
        except LLMUnavailable as e:
            fallback["note"] = f"LLM offline, used rule-based commentary ({e})"
            return fallback
        except DataLocalisationError as e:  # misconfigured foreign endpoint: never send, fall back safely
            fallback["note"] = f"BLOCKED by data-localisation guard: {e}"
            return fallback
        text = masker.unmask(text)
        bad = numeric_guard(text, facts)
        if len(bad) <= 3:
            break
        rejected.append(bad)
    else:  # too many unverifiable numbers in every attempt: do not publish
        fallback["note"] = f"LLM output rejected by numeric guard in {attempts} attempts (unverified: {rejected[-1][:10]})"
        return fallback
    return {"text": text, "source": f"llm:{llm.model}", "unverified_numbers": bad, "facts": facts,
            "note": f"accepted on attempt {attempt}"}
