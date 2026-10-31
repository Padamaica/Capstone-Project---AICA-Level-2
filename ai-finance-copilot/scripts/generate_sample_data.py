"""Generate a realistic, fully balanced double-entry General Ledger + Budget for testing.

Use synthetic data during development so real client ledgers stay out of dev machines.

Output:
    data/sample/gl.csv      date, voucher_no, voucher_type, account, party, debit, credit, cost_center, narration
    data/sample/budget.csv  month, category, amount

Contains deliberate anomalies for the co-pilot to detect:
    * a duplicate vendor payment (Feb 2026)
    * a professional-fees spike (Jun 2026)
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sample"
rng = np.random.default_rng(42)

START = date(2025, 4, 1)
END = date(2026, 9, 30)
BANK = "HDFC Bank Current A/c"

CUSTOMERS = {  # name: (credit days, extra delay mean, export?)
    "Apex Retail Ltd": (30, 5, False),
    "Bharat Distributors": (45, 20, False),
    "Coastal Traders": (30, 2, False),
    "Deccan Industries": (60, 35, False),
    "Eastern Exports Co": (45, 10, True),
    "Futura Engineering": (30, 8, False),
    "Global Parts GmbH": (60, 5, True),
    "Himalaya Stores": (30, 50, False),
}
VENDORS = {
    "Steelcore Metals": 30,
    "PolyChem Supplies": 45,
    "Prime Packaging": 30,
    "Unity Logistics": 15,
    "Vega Components": 45,
}

rows: list[dict] = []
counters: dict[str, int] = {}


def vno(prefix: str, d: date) -> str:
    counters[prefix] = counters.get(prefix, 0) + 1
    fy = d.year if d.month >= 4 else d.year - 1
    return f"{prefix}/{fy}-{str(fy + 1)[2:]}/{counters[prefix]:05d}"


def post(d: date, vtype: str, prefix: str, lines: list[tuple], narration: str = "", cc: str = "HO") -> None:
    """lines = [(account, party, debit, credit), ...] must balance."""
    dr = round(sum(l[2] for l in lines), 2)
    cr = round(sum(l[3] for l in lines), 2)
    assert abs(dr - cr) < 0.01, (d, vtype, lines)
    no = vno(prefix, d)
    for acc, party, debit, credit in lines:
        rows.append(dict(date=d.isoformat(), voucher_no=no, voucher_type=vtype, account=acc, party=party or "",
                         debit=round(debit, 2), credit=round(credit, 2), cost_center=cc, narration=narration))


def month_starts(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def rand_day(m: date) -> date:
    return m + timedelta(days=int(rng.integers(0, month_end(m).day)))


SEASON = {1: 1.10, 2: 1.12, 3: 1.25, 4: 0.90, 5: 0.92, 6: 0.95, 7: 0.97, 8: 1.00, 9: 1.02, 10: 1.08, 11: 1.05, 12: 1.03}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # Opening balances
    post(START, "Journal", "JV", [
        ("Plant & Machinery", "", 12_000_000, 0),
        (BANK, "", 10_000_000, 0),
        ("Share Capital", "", 0, 15_000_000),
        ("Term Loan - SBI", "State Bank of India", 0, 7_000_000),
    ], "Opening balances FY 2025-26")

    loan_balance = 7_000_000.0
    gross_block = 12_000_000.0
    pending_receipts: list[tuple] = []
    pending_payments: list[tuple] = []
    budget_rows = []

    for i, m in enumerate(month_starts(START, END)):
        me = month_end(m)
        growth = 1.018 ** i
        base_rev = 8_000_000 * growth * SEASON[m.month]
        month_rev = month_cogs = month_opex = 0.0
        out_gst = in_gst = 0.0

        # ---- Sales ----
        n_inv = int(rng.integers(22, 32))
        weights = rng.dirichlet(np.ones(n_inv))
        for w in weights:
            cust = rng.choice(list(CUSTOMERS))
            terms, delay, export = CUSTOMERS[cust]
            d = rand_day(m)
            amt = round(base_rev * w * rng.uniform(0.95, 1.05), 2)
            if export:
                post(d, "Sales", "SL", [("Sundry Debtors", cust, amt, 0), ("Sales - Export", "", 0, amt)],
                     f"Export invoice to {cust}", "Exports")
                total = amt
            else:
                gst = round(amt * 0.18, 2)
                total = round(amt + gst, 2)
                post(d, "Sales", "SL", [("Sundry Debtors", cust, total, 0), ("Sales - Domestic", "", 0, amt),
                                        ("Output GST", "", 0, gst)], f"Tax invoice to {cust}", "Domestic")
                out_gst += gst
            month_rev += amt
            pay_date = d + timedelta(days=terms + max(0, int(rng.normal(delay, 7))))
            pending_receipts.append((pay_date, cust, total))

        # ---- Purchases (COGS ~ 54-57%) ----
        purch_total = month_rev * rng.uniform(0.50, 0.53)
        for w in rng.dirichlet(np.ones(10)):
            vend = rng.choice(list(VENDORS)[:3] + ["Vega Components", "PolyChem Supplies"])
            d = rand_day(m)
            amt = round(purch_total * w, 2)
            gst = round(amt * 0.18, 2)
            post(d, "Purchase", "PU", [("Purchases - Raw Material", vend, amt, 0), ("Input GST", "", gst, 0),
                                       ("Sundry Creditors", vend, 0, round(amt + gst, 2))], f"Purchase bill {vend}")
            in_gst += gst
            month_cogs += amt
            pending_payments.append((d + timedelta(days=VENDORS[vend] + int(rng.integers(0, 10))), vend, round(amt + gst, 2)))
        freight = round(month_rev * rng.uniform(0.02, 0.03), 2)
        post(me - timedelta(days=3), "Payment", "PY", [("Freight Inward", "Unity Logistics", freight, 0), (BANK, "", 0, freight)],
             "Freight inward for the month")
        month_cogs += freight

        # ---- Operating expenses ----
        salary = round(1_150_000 * (1.10 if m >= date(2026, 4, 1) else 1.0) * rng.uniform(0.98, 1.02), 2)
        prof_fees = round(rng.uniform(80_000, 120_000), 2)
        if m == date(2026, 6, 1):
            prof_fees = 950_000.00  # anomaly: one-off consulting spike
        opex = [
            ("Salaries & Wages", "", salary, "Salaries for the month", "HO"),
            ("Staff Welfare", "", round(rng.uniform(40_000, 70_000), 2), "Staff welfare", "HO"),
            ("Rent", "Sai Properties (PAN AAKPS1234K)", 250_000.00, "Factory rent", "Factory"),
            ("Electricity", "MSEDCL", round(rng.uniform(150_000, 220_000), 2), "Power bill", "Factory"),
            ("Professional Fees", "KPS & Associates", prof_fees, "Audit/consulting fees", "HO"),
            ("Software Subscriptions", "", round(rng.uniform(35_000, 45_000), 2), "ERP & SaaS licences", "HO"),
            ("Advertising", "", round(rng.uniform(150_000, 300_000), 2), "Digital marketing", "Sales"),
            ("Travel & Conveyance", "", round(rng.uniform(60_000, 120_000), 2), "Sales travel", "Sales"),
        ]
        for acc, party, amt, narr, cc in opex:
            pay_day = me if acc == "Salaries & Wages" else (m + timedelta(days=4) if acc == "Rent" else rand_day(m))
            post(pay_day, "Payment", "PY",
                 [(acc, party, amt, 0), (BANK, "", 0, amt)], narr, cc)
            month_opex += amt

        # ---- Capex in Oct 2025 ----
        if m == date(2025, 10, 1):
            post(date(2025, 10, 15), "Payment", "PY", [("Plant & Machinery", "Vega Components", 2_500_000, 0), (BANK, "", 0, 2_500_000)],
                 "New CNC machine")
            gross_block += 2_500_000

        # ---- Depreciation, interest, loan repayment, interest income ----
        dep = round(gross_block * 0.15 / 12, 2)
        post(me, "Journal", "JV", [("Depreciation", "", dep, 0), ("Accumulated Depreciation", "", 0, dep)], "Monthly depreciation")
        interest = round(loan_balance * 0.095 / 12, 2)
        post(me, "Payment", "PY", [("Interest on Term Loan", "State Bank of India", interest, 0), (BANK, "", 0, interest)], "Loan interest")
        post(me, "Payment", "PY", [("Term Loan - SBI", "State Bank of India", 100_000, 0), (BANK, "", 0, 100_000)], "Loan EMI principal")
        loan_balance -= 100_000
        int_inc = round(rng.uniform(15_000, 30_000), 2)
        post(me, "Receipt", "RC", [(BANK, "", int_inc, 0), ("Interest Income", "", 0, int_inc)], "Sweep FD interest")

        # ---- Settle receipts / payments that fall in this month ----
        for p in [x for x in pending_receipts if x[0] <= me]:
            post(p[0], "Receipt", "RC", [(BANK, "", p[2], 0), ("Sundry Debtors", p[1], 0, p[2])], f"Receipt from {p[1]}")
            pending_receipts.remove(p)
        for p in [x for x in pending_payments if x[0] <= me]:
            post(p[0], "Payment", "PY", [("Sundry Creditors", p[1], p[2], 0), (BANK, "", 0, p[2])], f"Payment to {p[1]}")
            pending_payments.remove(p)
            if m == date(2026, 2, 1) and p[1] == "Steelcore Metals" and not any(r["narration"].startswith("Payment to Steelcore Metals (dup)") for r in rows):
                dup_date = p[0] + timedelta(days=2)  # anomaly: duplicate payment
                post(dup_date, "Payment", "PY", [("Sundry Creditors", p[1], p[2], 0), (BANK, "", 0, p[2])],
                     f"Payment to {p[1]} (dup) GSTIN 27AABCS1234F1Z5")

        # ---- GST set-off and payment ----
        setoff = round(min(out_gst, in_gst), 2)
        lines = [("Output GST", "", setoff, 0), ("Input GST", "", 0, setoff)]
        net = round(out_gst - setoff, 2)
        if net > 0:
            lines += [("Output GST", "", net, 0), (BANK, "", 0, net)]
        post(me, "Journal", "JV", lines, "GST set-off & payment (GSTR-3B)")

        # ---- Tax provision 25% of PBT ----
        pbt = month_rev + int_inc - month_cogs - month_opex - dep - interest
        if pbt > 0:
            tax = round(pbt * 0.25, 2)
            post(me, "Journal", "JV", [("Income Tax", "", tax, 0), ("Provision for Tax", "", 0, tax)], "Tax provision")

        # ---- Advance tax paid quarterly (clears provision) ----
        if m.month in (6, 9, 12, 3):
            prov = sum(r["credit"] - r["debit"] for r in rows if r["account"] == "Provision for Tax")
            if prov > 0:
                post(date(m.year, m.month, 15), "Payment", "PY", [("Provision for Tax", "Income Tax Dept", round(prov, 2), 0),
                                                                 (BANK, "", 0, round(prov, 2))], "Advance tax paid")

        # ---- Budget (prepared before the year: smoother, slightly optimistic) ----
        bud_rev = 8_200_000 * (1.02 ** i) * SEASON[m.month]
        month_key = m.strftime("%Y-%m")
        budget_rows += [
            (month_key, "Revenue", bud_rev),
            (month_key, "COGS", bud_rev * 0.535),
            (month_key, "Employee Cost", 1_200_000 * (1.10 if m >= date(2026, 4, 1) else 1.0)),
            (month_key, "Admin Expenses", 560_000),
            (month_key, "Marketing Expenses", 300_000),
            (month_key, "Depreciation", gross_block * 0.15 / 12),
            (month_key, "Finance Cost", loan_balance * 0.095 / 12),
            (month_key, "Other Income", 20_000),
        ]

    gl = pd.DataFrame(rows).sort_values(["date", "voucher_no"]).reset_index(drop=True)
    gl.to_csv(OUT / "gl.csv", index=False)
    bud = pd.DataFrame(budget_rows, columns=["month", "category", "amount"])
    bud["amount"] = bud["amount"].round(0)
    bud.to_csv(OUT / "budget.csv", index=False)
    print(f"GL rows: {len(gl):,} | Dr {gl.debit.sum():,.2f} = Cr {gl.credit.sum():,.2f} | budget rows: {len(bud)}")
    print(f"Written to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
