"""'Ask your data': natural language -> safe read-only SQL -> answer.

Safety layers:
 1. The LLM sees only the schema, never raw rows, when writing SQL.
 2. SQL validator: single SELECT/WITH statement only, no PRAGMA/ATTACH/DDL/DML.
 3. Executed on a read-only SQLite connection, with a row limit and a time limit.
 4. Result rows are PII-masked before being summarised by the LLM.
Without an LLM, a keyword router answers common questions with pre-written SQL.
"""
from __future__ import annotations

import re
import time

import pandas as pd

from ..config import settings
from ..storage import SCHEMA_DOC, connect
from .llm import LLMUnavailable, get_llm
from .pii import PIIMasker
from ..utils import fmt_inr

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|trigger|load_extension)\b", re.I)

SQL_SYSTEM = f"""You translate finance questions into a single SQLite SELECT query.
{SCHEMA_DOC}
Rules: return ONLY the SQL, no explanation, no markdown fences. Use only the tables/columns above.
Prefer the pnl table for P&L questions and balance_sheet for balances (cash line_item is 'Cash & Bank').
Months are 'YYYY-MM' strings: never use DATE('now'); for 'last N months' use ORDER BY month DESC LIMIT N.
The pnl table has ONLY the columns month, line_item, amount. Expenses are P&L categories only
(statement='PL'), never balance-sheet accounts. Limit results to 50 rows."""

ANSWER_SYSTEM = """You are a finance co-pilot. Answer the user's question using ONLY the query result provided.
Amounts are already formatted in INR lakh (L) / crore (Cr): copy them exactly as written and never convert,
round or invent numbers. If the result is empty, say so. Be brief (max 6 bullet points)."""

_LAST = "(SELECT MAX(month) FROM pnl)"
CANNED = [
    (r"revenue|sales|turnover",
     "SELECT month, amount AS revenue FROM pnl WHERE line_item='Revenue' ORDER BY month DESC LIMIT 6"),
    (r"profit|\bpat\b|ebitda|margin",
     "SELECT month, SUM(CASE WHEN line_item='Revenue' THEN amount END) AS revenue, SUM(CASE WHEN line_item='EBITDA' THEN amount END) AS ebitda, "
     "SUM(CASE WHEN line_item='PAT' THEN amount END) AS pat FROM pnl GROUP BY month ORDER BY month DESC LIMIT 6"),
    (r"top (customer|client)|largest customer",
     "SELECT party, ROUND(SUM(debit),2) AS billed FROM gl WHERE category='Receivables' AND party<>'' GROUP BY party ORDER BY billed DESC LIMIT 10"),
    (r"overdue|receivable|debtor|collection",
     "SELECT party, ROUND(SUM(open_amount),2) AS total_open, ROUND(SUM(CASE WHEN age_days>60 THEN open_amount ELSE 0 END),2) AS over_60_days, "
     "MAX(age_days) AS oldest_days FROM ar_ageing GROUP BY party ORDER BY over_60_days DESC, total_open DESC LIMIT 10"),
    (r"payable|creditor|vendor|supplier",
     "SELECT party, ROUND(SUM(open_amount),2) AS total_open, MAX(age_days) AS oldest_days FROM ap_ageing GROUP BY party ORDER BY total_open DESC LIMIT 10"),
    (r"expense|cost|spend",
     "SELECT account, category, ROUND(SUM(debit-credit),2) AS amount FROM gl WHERE statement='PL' AND category NOT IN ('Revenue','Other Income') "
     f"AND month={_LAST} GROUP BY account, category ORDER BY amount DESC LIMIT 5"),
    (r"cash|bank|liquidity",
     "SELECT month, amount AS closing_cash FROM balance_sheet WHERE line_item='Cash & Bank' ORDER BY month DESC LIMIT 6"),
]

_AMOUNT_COL = re.compile(r"amount|revenue|ebitda|pat|billed|open|cash|cost|expense|total|balance|over_", re.I)


def answer_guard(answer: str, source_text: str) -> list[str]:
    """Every number in the answer (incl. years/months) must appear in the query result shown to the LLM."""
    toks = lambda t: {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", t)}  # noqa: E731
    allowed = toks(source_text)
    return sorted(n for n in toks(answer) if n not in allowed and not (n.isdigit() and int(n) <= 12))


def completeness_guard(answer: str, df: pd.DataFrame, top_n: int = 5) -> list[str]:
    """The key (first column) of each of the top rows must appear in the answer: no silent omissions."""
    if df.empty:
        return []
    keys = [str(k) for k in df.iloc[:top_n, 0].tolist()]
    low = answer.lower()
    missing = [k for k in keys if k and k.lower() not in low]
    if missing:
        return missing
    pos = [low.find(k.lower()) for k in keys if k]
    if pos != sorted(pos):  # same rows but re-ranked: the order is part of the answer
        return ["<order changed>"]
    return []


def python_summary(df: pd.DataFrame) -> str:
    f = _format_for_llm(df.head(10))
    cols = list(f.columns)
    return "\n".join(f"- **{row[cols[0]]}**: " + ", ".join(f"{c.replace('_', ' ')} {row[c]}" for c in cols[1:])
                     for _, row in f.iterrows())


def _canned_sql(question: str) -> str | None:
    for pat, sql in CANNED:
        if re.search(pat, question, re.I):
            return sql
    return None


def _format_for_llm(df: pd.DataFrame) -> pd.DataFrame:
    """Python formats every amount (INR L/Cr) so the LLM only copies, never converts."""
    out = df.copy()
    for c in out.columns:
        if _AMOUNT_COL.search(str(c)) and pd.api.types.is_numeric_dtype(out[c]):
            out[c] = out[c].map(fmt_inr)
    return out


def validate_sql(sql: str) -> str:
    s = sql.strip().strip("`")
    s = re.sub(r"^sql\s*", "", s, flags=re.I).strip().rstrip(";").strip()
    if ";" in s:
        raise ValueError("Only a single statement is allowed.")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise ValueError("Only SELECT queries are allowed.")
    if FORBIDDEN.search(s):
        raise ValueError("Query contains a forbidden keyword.")
    return s


def run_sql(sql: str, max_rows: int = 500, timeout_s: float = 5.0) -> pd.DataFrame:
    s = validate_sql(sql)
    con = connect(read_only=True)
    start = time.time()
    con.set_progress_handler(lambda: 1 if time.time() - start > timeout_s else 0, 10_000)
    try:
        return pd.read_sql_query(f"SELECT * FROM ({s}) LIMIT {int(max_rows)}", con)
    finally:
        con.close()


def _extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip()


def ask(question: str, party_names: list[str] | None = None, use_llm: bool = True) -> dict:
    """Hybrid router: known question types run pre-tested SQL (deterministic numbers); the LLM writes SQL only
    for new question types. Either way the LLM only summarises Python-formatted results."""
    llm = get_llm() if use_llm else None
    canned = _canned_sql(question)
    note = ""
    sql, df, route = None, pd.DataFrame(), ""
    if canned:
        sql, df, route = canned, run_sql(canned), "verified SQL"
    elif llm is not None:
        prompt = question
        for attempt in (1, 2):  # one self-correction round: the DB error is fed back to the LLM
            try:
                cand = validate_sql(_extract_sql(llm.chat(SQL_SYSTEM, prompt)))
                df, sql, route = run_sql(cand), cand, f"LLM-written SQL (attempt {attempt})"
                break
            except LLMUnavailable as e:
                note = f"LLM offline ({e})."
                break
            except Exception as e:  # noqa: BLE001 - invalid / failing SQL
                note = f"LLM SQL failed ({type(e).__name__}: {e})."
                prompt = f"{question}\n\nYour previous SQL failed with: {e}. Write a corrected query."
    if sql is None:
        return {"answer": "I couldn't map that question. Try asking about revenue, profit, expenses, cash, "
                          "receivables, payables or top customers.", "sql": None, "data": pd.DataFrame(),
                "source": "rules", "note": note or "LLM disabled; used keyword router."}
    if llm is None:
        return {"answer": f"Here is the data matching your question ({len(df)} rows).", "sql": sql, "data": df,
                "source": "rules", "note": "LLM disabled; used keyword router."}
    if df.empty:
        return {"answer": "The query returned no rows.", "sql": sql, "data": df, "source": f"llm:{llm.model}",
                "note": f"{route}; empty result"}
    try:
        masker = PIIMasker((party_names or []) if settings.mask_pii_before_llm else [])
        preview = masker.mask(_format_for_llm(df.head(50)).to_csv(index=False))
        answer = masker.unmask(llm.chat(ANSWER_SYSTEM, f"Question: {question}\n\nQuery result (CSV):\n{preview}"))
        bad = answer_guard(answer, masker.unmask(preview))
        missing = completeness_guard(answer, df)
        if bad or missing:  # LLM changed a number or dropped a top row: publish the Python-built answer instead
            why = f"numbers not in data {bad[:5]}" if bad else f"omitted rows {missing[:5]}"
            route += f"; LLM answer rejected ({why}), Python summary used"
            answer = python_summary(df)
    except LLMUnavailable as e:
        return {"answer": f"Here is the data matching your question ({len(df)} rows).", "sql": sql, "data": df,
                "source": "rules", "note": f"LLM offline ({e})"}
    return {"answer": answer, "sql": sql, "data": df, "source": f"llm:{llm.model}", "note": route}
