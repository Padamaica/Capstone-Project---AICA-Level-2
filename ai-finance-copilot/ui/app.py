"""Streamlit front-end for the AI Finance Co-Pilot.

Run:  streamlit run ui/app.py
(Telemetry is disabled in .streamlit/config.toml for data localisation.)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot.ai import ask, get_llm  # noqa: E402
from copilot.config import settings  # noqa: E402
from copilot.pipeline import generate_reports, run_analysis  # noqa: E402
from copilot.utils import fmt_inr, month_label  # noqa: E402

st.set_page_config(page_title="AI Finance Co-Pilot", page_icon="📊", layout="wide")


def lakh(df: pd.DataFrame) -> pd.DataFrame:
    return (df / 1e5).round(2)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("📊 AI Finance Co-Pilot")
    st.caption(f"{settings.company_name}")
    llm = get_llm()
    llm_ok = bool(llm and llm.health())
    st.markdown(f"**LLM:** `{settings.llm_provider}` / `{settings.llm_model}` "
                f"{'🟢 online' if llm_ok else '🔴 offline (rule-based mode)'}")
    st.markdown(f"**Outbound guard:** {'🔒 on' if settings.block_outbound_network else '⚠️ off'} &nbsp; "
                f"**PII masking:** {'on' if settings.mask_pii_before_llm else 'off'}")
    st.divider()
    src = st.radio("Data source", ["Excel template (1 file)", "Sample data", "Upload files"])
    gl_file = bud_file = map_file = xl_file = None
    if src == "Excel template (1 file)":
        xl_file = st.file_uploader("MIS input workbook (sheets: GL, Budget, Mapping)", type=["xlsx"])
        st.caption("Blank template: templates/MIS_Input_Template.xlsx")
    if src == "Upload files":
        gl_file = st.file_uploader("General Ledger / Day Book (CSV, XLSX, Tally XML)", type=["csv", "xlsx", "xls", "xml"])
        bud_file = st.file_uploader("Budget (month, category, amount)", type=["csv", "xlsx"])
        map_file = st.file_uploader("Chart-of-accounts mapping (optional)", type=["csv", "xlsx"])
    month = st.text_input("Month (YYYY-MM, blank = latest)", "")
    use_llm = st.toggle("Use local LLM for commentary", value=llm_ok)
    run = st.button("▶ Run analysis", type="primary", use_container_width=True)

if run:
    try:
        with st.spinner("Crunching the ledger..."):
            if src == "Excel template (1 file)":
                if xl_file is None:
                    st.error("Upload the filled MIS input workbook first.")
                    st.stop()
                from copilot.ingestion.workbook import split_input_workbook
                parts = split_input_workbook(xl_file)
                res = run_analysis(parts.gl, parts.budget, parts.mapping, month or None, gl_name="gl.csv",
                                   budget_name="budget.csv", use_llm=use_llm, user="ui")
            elif src == "Sample data":
                res = run_analysis(ROOT / "data/sample/gl.csv", ROOT / "data/sample/budget.csv", None, month or None,
                                   use_llm=use_llm, user="ui")
            else:
                if gl_file is None:
                    st.error("Upload a GL file first.")
                    st.stop()
                res = run_analysis(gl_file, bud_file, map_file, month or None, gl_name=gl_file.name,
                                   budget_name=bud_file.name if bud_file else None, use_llm=use_llm, user="ui")
        st.session_state["res"] = res
        st.session_state.pop("chat", None)
    except ValueError as e:
        st.error(str(e))

res = st.session_state.get("res")
if res is None:
    st.header("Welcome 👋")
    st.markdown("""
1. Upload the **filled MIS input workbook** (one Excel: GL + Budget + Mapping), or choose **Sample data**.
2. Click **Run analysis**: statements, ratios, variance, ageing, anomalies and forecast are computed in Python.
3. The **local LLM** writes the commentary and answers questions. Data never leaves this server.
4. Download the **Excel MIS pack** and **PDF board pack**.
""")
    st.stop()

m, months = res.month, res.months
prev = months[-2] if len(months) > 1 else m
tabs = st.tabs(["🏠 Dashboard", "📑 Statements", "🎯 Budget vs Actual", "⏳ Ageing", "🚨 Anomalies", "🔮 Forecast",
                "💬 Ask Co-Pilot", "📥 Reports", "✅ Data Quality"])

# ------------------------------------------------------------------ dashboard
with tabs[0]:
    st.subheader(f"MIS Dashboard: {month_label(m)}")
    c = st.columns(5)
    for i, line in enumerate(["Revenue", "Gross Profit", "EBITDA", "PAT"]):
        cur, pv = res.pnl.loc[line, m], res.pnl.loc[line, prev]
        c[i].metric(line, fmt_inr(cur), f"{(cur - pv) / abs(pv) * 100:+.1f}% MoM" if pv else None)
    cash, pcash = res.ratios.loc["Cash & Bank", m], res.ratios.loc["Cash & Bank", prev]
    c[4].metric("Cash & Bank", fmt_inr(cash), fmt_inr(cash - pcash))
    c = st.columns(5)
    for i, k in enumerate(["Gross Margin %", "EBITDA Margin %", "DSO (days)", "DPO (days)", "Current Ratio (x)"]):
        cur, pv = res.ratios.loc[k, m], res.ratios.loc[k, prev]
        c[i].metric(k, f"{cur:.1f}", f"{cur - pv:+.1f}", delta_color="inverse" if "DSO" in k else "normal")
    l, r = st.columns(2)
    l.markdown("**Revenue / EBITDA / PAT (₹ lakh)**")
    l.line_chart(lakh(res.pnl.loc[["Revenue", "EBITDA", "PAT"]]).T)
    r.markdown("**Closing cash (₹ lakh)**")
    r.area_chart(lakh(res.ratios.loc[["Cash & Bank"]]).T)
    st.markdown(f"#### 🧠 Management commentary  `{res.commentary.get('source')}`")
    if res.commentary.get("note"):
        st.caption(res.commentary["note"])
    st.markdown(res.commentary.get("text", ""))
    if res.commentary.get("unverified_numbers"):
        st.warning(f"Numbers not found in source facts: {res.commentary['unverified_numbers']}")

# ------------------------------------------------------------------ statements
with tabs[1]:
    unit = st.radio("Units", ["₹ lakh", "₹"], horizontal=True)
    f = lakh if unit == "₹ lakh" else (lambda d: d)
    st.markdown("#### Profit & Loss")
    st.dataframe(f(res.pnl), use_container_width=True)
    st.markdown("#### Balance Sheet")
    st.dataframe(f(res.balance_sheet), use_container_width=True)
    st.markdown("#### Cash Flow (indirect)")
    st.dataframe(f(res.cash_flow), use_container_width=True)
    st.markdown("#### Ratios")
    st.dataframe(res.ratios, use_container_width=True)

# ------------------------------------------------------------------ BvA
with tabs[2]:
    if res.bva_month is None:
        st.info("Upload a budget file to see variance analysis.")
    else:
        def colour(row):
            col = "#C6EFCE" if row["status"] == "Favourable" else ("#FFC7CE" if row["flag"] else "#FFEB9C")
            return [f"background-color: {col}" if c == "status" else "" for c in row.index]
        st.markdown(f"#### {month_label(m)}")
        st.dataframe(res.bva_month.style.apply(colour, axis=1).format(precision=0), use_container_width=True)
        st.markdown("#### Year to date")
        st.dataframe(res.bva_ytd.style.apply(colour, axis=1).format(precision=0), use_container_width=True)

# ------------------------------------------------------------------ ageing
with tabs[3]:
    a, b = st.columns(2)
    a.markdown("#### Receivables (AR)")
    a.dataframe(res.ar_summary, use_container_width=True, hide_index=True)
    a.bar_chart(lakh(res.ar_summary[res.ar_summary.party != "TOTAL"].set_index("party").drop(columns="Total")))
    b.markdown("#### Payables (AP)")
    b.dataframe(res.ap_summary, use_container_width=True, hide_index=True)
    with st.expander("Open AR invoices"):
        st.dataframe(res.ar_detail, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ anomalies
with tabs[4]:
    st.markdown(f"#### {len(res.anomalies)} items to review")
    st.dataframe(res.anomalies, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ forecast
with tabs[5]:
    if res.forecast is not None:
        hist = res.pnl.loc["Revenue"].rename("Actual")
        fc = res.forecast.loc[["Revenue", "Revenue Low (80%)", "Revenue High (80%)"]].T
        st.line_chart(lakh(pd.concat([hist, fc], axis=1)))
        st.dataframe(lakh(res.forecast), use_container_width=True)

# ------------------------------------------------------------------ chat
with tabs[6]:
    st.caption("Questions are turned into read-only SQL on the local database. Results are PII-masked before reaching the LLM.")
    st.session_state.setdefault("chat", [])
    for msg in st.session_state["chat"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sql"):
                st.code(msg["sql"], language="sql")
            if msg.get("data") is not None and not msg["data"].empty:
                st.dataframe(msg["data"], use_container_width=True, hide_index=True)
    q = st.chat_input("e.g. Which customers have dues older than 60 days?")
    if q:
        st.session_state["chat"].append({"role": "user", "content": q})
        out = ask(q, res.party_names, use_llm=use_llm)
        st.session_state["chat"].append({"role": "assistant", "content": out["answer"] + (f"\n\n_{out['note']}_" if out.get("note") else ""),
                                         "sql": out.get("sql"), "data": out.get("data")})
        st.rerun()

# ------------------------------------------------------------------ reports
with tabs[7]:
    if st.button("Generate MIS pack (Excel + PDF)", type="primary"):
        with st.spinner("Building reports..."):
            st.session_state["paths"] = generate_reports(res, user="ui")
    paths = st.session_state.get("paths")
    if paths:
        c1, c2 = st.columns(2)
        c1.download_button("⬇ Excel MIS pack", paths["excel"].read_bytes(), paths["excel"].name,
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        c2.download_button("⬇ PDF board pack", paths["pdf"].read_bytes(), paths["pdf"].name, "application/pdf",
                           use_container_width=True)

# ------------------------------------------------------------------ DQ
with tabs[8]:
    v = res.validation
    (st.success if v.ok else st.error)("Validation passed" if v.ok else "Validation errors found")
    for e in v.errors:
        st.error(e)
    for w in v.warnings:
        st.warning(w)
    for i in v.info:
        st.info(i)
