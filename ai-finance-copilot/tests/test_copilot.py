"""Tests: run with `pytest -q` or `python tests/test_copilot.py` (no pytest needed).

Finance software lives or dies on accuracy. Every calculation here gets a test.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot.ai.commentary import numeric_guard  # noqa: E402
from copilot.ai.nl_query import run_sql, validate_sql  # noqa: E402
from copilot.ai.pii import PIIMasker  # noqa: E402
from copilot.engine import (ageing, balance_sheet_monthly, budget_vs_actual, cash_flow_monthly, detect_anomalies,  # noqa: E402
                            enrich, forecast_series, pnl_monthly)
from copilot.ingestion import load_coa_mapping, load_gl, validate_gl  # noqa: E402
from copilot.localisation import DataLocalisationError, assert_local_endpoint  # noqa: E402
from copilot.pipeline import generate_reports, run_analysis  # noqa: E402
from copilot.utils import fmt_inr, indian_number  # noqa: E402

GL = ROOT / "data/sample/gl.csv"
BUD = ROOT / "data/sample/budget.csv"
MAP = ROOT / "config/coa_mapping.csv"


def _mini_gl() -> pd.DataFrame:
    rows = [
        ("2026-04-01", "JV1", "Bank", "", 1000, 0, "Opening"), ("2026-04-01", "JV1", "Capital", "", 0, 1000, "Opening"),
        ("2026-04-05", "S1", "Debtors", "A", 500, 0, ""), ("2026-04-05", "S1", "Sales", "", 0, 500, ""),
        ("2026-04-20", "S2", "Debtors", "A", 300, 0, ""), ("2026-04-20", "S2", "Sales", "", 0, 300, ""),
        ("2026-04-25", "P1", "Rent", "", 100, 0, ""), ("2026-04-25", "P1", "Bank", "", 0, 100, ""),
        ("2026-05-10", "R1", "Bank", "", 600, 0, ""), ("2026-05-10", "R1", "Debtors", "A", 0, 600, ""),
    ]
    df = pd.DataFrame(rows, columns=["date", "voucher_no", "account", "party", "debit", "credit", "narration"])
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["voucher_type"] = ""
    df["cost_center"] = ""
    return df


MINI_MAP = pd.DataFrame([("Bank", "Cash & Bank", "BS"), ("Capital", "Share Capital", "BS"), ("Debtors", "Receivables", "BS"),
                         ("Sales", "Revenue", "PL"), ("Rent", "Admin Expenses", "PL")], columns=["account", "category", "statement"])


def test_mini_pnl_and_balance_sheet():
    e = enrich(_mini_gl(), MINI_MAP)
    p = pnl_monthly(e)
    assert p.loc["Revenue", "2026-04"] == 800
    assert p.loc["PAT", "2026-04"] == 700
    bs = balance_sheet_monthly(e, p)
    assert bs.loc["Check (should be 0)"].abs().max() < 0.01
    assert bs.loc["Receivables", "2026-05"] == 200
    cf = cash_flow_monthly(e, p, bs)
    assert cf.loc["Check vs Bank Movement (should be 0)"].abs().max() < 0.01
    assert cf.loc["Equity Raised"].abs().sum() == 0  # opening balance is not a cash flow


def test_fifo_ageing():
    e = enrich(_mini_gl(), MINI_MAP)
    det, summ = ageing(e, "2026-05-31", "AR")
    # receipt of 600 clears S1 (500) fully and 100 of S2 -> 200 open from 20-Apr
    assert len(det) == 1 and det.iloc[0]["open_amount"] == 200 and det.iloc[0]["age_days"] == 41
    assert summ.set_index("party").loc["TOTAL", "Total"] == 200


def test_sample_data_validates_and_balances():
    gl, m = load_gl(GL), load_coa_mapping(MAP)
    assert validate_gl(gl, m).ok
    e = enrich(gl, m)
    p = pnl_monthly(e)
    bs = balance_sheet_monthly(e, p)
    cf = cash_flow_monthly(e, p, bs)
    assert bs.loc["Check (should be 0)"].abs().max() < 1
    assert cf.loc["Check vs Bank Movement (should be 0)"].abs().max() < 1


def test_validation_catches_unbalanced_and_unmapped():
    g = _mini_gl()
    g.loc[2, "debit"] = 999
    g.loc[len(g)] = [pd.Timestamp("2026-05-11"), "X1", "Mystery", "", 5, 5, "", "2026-05", "", ""]
    r = validate_gl(g, MINI_MAP)
    assert not r.ok
    assert any("unbalanced" in x for x in r.errors) and any("not in the chart" in x for x in r.errors)


def test_budget_variance_sign_logic():
    e = enrich(_mini_gl(), MINI_MAP)
    p = pnl_monthly(e)
    bud = pd.DataFrame([("2026-04", "Revenue", 1000), ("2026-04", "Admin Expenses", 50)], columns=["month", "category", "amount"])
    v = budget_vs_actual(p, bud, "2026-04").set_index("line_item")
    assert v.loc["Revenue", "status"] == "Adverse" and v.loc["Revenue", "variance_pct"] == -20
    assert v.loc["Admin Expenses", "status"] == "Adverse" and v.loc["Admin Expenses", "flag"]


def test_anomalies_find_planted_issues():
    e = enrich(load_gl(GL), load_coa_mapping(MAP))
    a = detect_anomalies(e)
    assert ((a["type"] == "Possible duplicate payment") & (a["party"] == "Steelcore Metals")).any()
    assert ((a["type"] == "Expense spike") & (a["account"] == "Professional Fees")).any()
    assert not (a["party"].astype(str).str.contains("Sai Properties")).any()  # recurring rent is not a duplicate


def test_forecast_shape():
    s = pd.Series([100, 110, 120, 130, 140, 150], index=[f"2026-0{i}" for i in range(1, 7)])
    f = forecast_series(s, 3)
    assert list(f.index) == ["2026-07", "2026-08", "2026-09"]
    assert f["forecast"].iloc[0] > 150 and (f["high_80"] >= f["low_80"]).all()


def test_pii_masking_roundtrip():
    m = PIIMasker(["Steelcore Metals"])
    txt = "Paid Steelcore Metals GSTIN 27AABCS1234F1Z5 PAN AAKPS1234K mail a@b.com ph 9876543210 A/c No 123456789012"
    masked = m.mask(txt)
    for secret in ["Steelcore", "27AABCS1234F1Z5", "AAKPS1234K", "a@b.com", "9876543210", "123456789012"]:
        assert secret not in masked
    assert "Steelcore Metals" in m.unmask(masked)


def test_sql_guard():
    assert validate_sql("SELECT * FROM pnl;").lower().startswith("select")
    for bad in ["DROP TABLE gl", "SELECT 1; DELETE FROM gl", "PRAGMA table_info(gl)", "ATTACH 'x' AS y", "UPDATE gl SET debit=0"]:
        try:
            validate_sql(bad)
            raise AssertionError(f"should block: {bad}")
        except ValueError:
            pass


def test_localisation_guard():
    for ok in ["http://localhost:11434", "http://10.0.1.5:8000/v1", "http://ollama:11434", "http://192.168.1.20"]:
        assert_local_endpoint(ok)
    for bad in ["https://api.openai.com/v1", "https://api.anthropic.com", "https://generativelanguage.googleapis.com"]:
        try:
            assert_local_endpoint(bad)
            raise AssertionError(f"should block {bad}")
        except DataLocalisationError:
            pass


def test_numeric_guard():
    facts = {"revenue": "₹1.11 Cr", "growth": "+5.5%"}
    assert numeric_guard("Revenue was ₹1.11 Cr, up 5.5% in 2026.", facts) == []
    assert numeric_guard("Revenue was ₹1.45 Cr.", facts) == ["1.45"]


def test_indian_formatting():
    assert indian_number(12345678.9) == "1,23,45,679"
    assert indian_number(-1234) == "-1,234"
    assert fmt_inr(12_500_000) == "₹1.25 Cr" and fmt_inr(250_000) == "₹2.50 L"


def test_end_to_end_pipeline_and_reports(tmp_path: Path | None = None):
    out = tmp_path or (ROOT / "output" / "_test")
    res = run_analysis(GL, BUD, None, "2026-06", use_llm=False, user="test")
    assert res.month == "2026-06" and res.months[-1] == "2026-06"  # no look-ahead
    assert res.commentary["source"] == "rules" and "### Headline" in res.commentary["text"]
    paths = generate_reports(res, out)
    assert paths["excel"].stat().st_size > 10_000 and paths["pdf"].stat().st_size > 10_000
    df = run_sql("SELECT COUNT(*) AS n FROM pnl WHERE line_item='Revenue'")
    assert int(df.n.iloc[0]) == 15


def test_qa_answer_guard_rejects_changed_numbers():
    from copilot.ai.nl_query import answer_guard
    src = "month,revenue\n2026-05,₹92.33 L\n2026-04,₹90.12 L"
    assert answer_guard("- 2026-05: ₹92.33 L\n- 2026-04: ₹90.12 L", src) == []
    assert "2025" in answer_guard("- 2025-05: ₹92.33 L", src)          # wrong year
    assert "9.01" in answer_guard("Revenue was ₹9.01 Cr", src)         # wrong unit conversion
    from copilot.ai.nl_query import completeness_guard
    df = pd.DataFrame({"party": ["Bharat Distributors", "Deccan Industries", "Himalaya Stores"], "amt": [6.5, 3.9, 1.2]})
    assert completeness_guard("Bharat Distributors 6.5, Himalaya Stores 1.2", df) == ["Deccan Industries"]
    assert completeness_guard("Bharat Distributors, Himalaya Stores, Deccan Industries", df) == ["<order changed>"]
    assert completeness_guard("Bharat Distributors, Deccan Industries, Himalaya Stores", df) == []


def test_qa_routes_known_questions_to_verified_sql():
    from copilot.ai.nl_query import _canned_sql, _format_for_llm
    assert "Cash & Bank" in _canned_sql("How has closing cash moved?")
    assert "statement='PL'" in _canned_sql("top 5 expenses this month")
    assert _canned_sql("What was depreciation in each of the last 3 months?") is None  # goes to LLM
    out = _format_for_llm(pd.DataFrame({"month": ["2026-09"], "revenue": [11062189.81]}))
    assert out.revenue.iloc[0] == "₹1.11 Cr"


def test_single_excel_workbook_input():
    from copilot.ingestion.workbook import split_input_workbook
    from copilot.pipeline import run_analysis
    src = ROOT / "input" / "MIS_Input_Sample_Sep-2026.xlsx"
    if not src.exists():
        return  # template not built in this checkout
    parts = split_input_workbook(src)
    assert parts.sheets_found == {"gl": "GL", "budget": "Budget", "mapping": "Mapping"}
    res = run_analysis(parts.gl, parts.budget, parts.mapping, None, gl_name="gl.csv", budget_name="budget.csv",
                       persist=False, with_commentary=False)
    assert res.validation.ok and res.month == "2026-09"
    assert abs(res.pnl.loc["Revenue", "2026-09"] - 11062189.81) < 1


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
