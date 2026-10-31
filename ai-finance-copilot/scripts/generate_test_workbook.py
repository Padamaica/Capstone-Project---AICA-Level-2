"""Generate a compact, fully balanced TEST workbook: exactly 500 GL lines + 60 budget lines.

Company: Sample Foods Pvt Ltd (synthetic). Period: Apr-2026 to Sep-2026 (H1 FY 2026-27).
Output: input/MIS_Input_Test_500_Lines.xlsx  (sheets README, GL, Budget, Mapping, Control_Totals, Lists)

Accounting design (all vouchers balance by construction):
  * Opening balances 01-Apr-2026 in one 'Opening' JV (party-wise debtors/creditors for ageing).
  * Domestic sales @18% GST, export sales zero-rated (LUT). Purchases @18% input GST.
  * Packing line (Jul) paid by SBI term-loan disbursement direct to the vendor.
  * GST: previous month's Output GST - Input GST paid on the 20th. TDS @10% on rent and professional fees, paid on the 7th.
  * Depreciation SLM 10% p.a. on gross block; capex added in Jul-2026, depreciated from Aug-2026.
  * Term loan @9.5% p.a.; principal Rs 5 L/month. Interest income on sweep FD credited to bank.
  * Inventory change JV each month-end (Dr/Cr Inventories vs Changes in Inventories, a COGS line).
  * Income tax provision @25.168% (sec. 115BAA) of monthly PBT; advance tax paid 15-Jun and 15-Sep.
Planted test cases: duplicate vendor payment (Jul), professional-fee spike (Aug), slow-paying customer.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_templates import GL_COLS, HDR_FILL, HDR_FONT, NAVY, build  # noqa: E402

TARGET_GL, TARGET_BUD = 500, 60
BANK = "HDFC Bank Current A/c"
MONTHS = pd.period_range("2026-04", "2026-09", freq="M")
TAX_RATE = 0.25168
rng = np.random.default_rng(2026)

CUSTOMERS = {  # name: (credit days, extra delay, monthly share of domestic sales)
    "Annapurna Retail LLP": (30, 3, 0.26),
    "Bharat Wholesale Co": (45, 5, 0.22),
    "City Mart Stores": (30, 2, 0.18),
    "Deccan Food Distributors": (60, 75, 0.14),   # slow payer -> overdue > 90 days
    "Eastern Supply Chain Ltd": (45, 8, 0.20),
}
EXPORT_CUSTOMER = ("Gulf Foods Trading FZE", 60, 0)
VENDORS = {"Krishna Agro Commodities": 30, "Sunrise Packaging Industries": 45, "Pune Chemicals & Additives": 30}
FREIGHT_VENDOR = "Swift Logistics"
SEASON = {4: 0.94, 5: 0.97, 6: 1.00, 7: 1.03, 8: 1.06, 9: 1.08}

MAPPING = [
    ("Sales - Domestic", "Revenue", "PL"), ("Sales - Export", "Revenue", "PL"), ("Interest Income", "Other Income", "PL"),
    ("Purchases - Raw Material", "COGS", "PL"), ("Freight Inward", "COGS", "PL"), ("Changes in Inventories", "COGS", "PL"),
    ("Salaries & Wages", "Employee Cost", "PL"), ("Staff Welfare", "Employee Cost", "PL"),
    ("Rent", "Admin Expenses", "PL"), ("Electricity", "Admin Expenses", "PL"), ("Professional Fees", "Admin Expenses", "PL"),
    ("Advertising", "Marketing Expenses", "PL"),
    ("Travel & Conveyance", "Marketing Expenses", "PL"), ("Depreciation", "Depreciation", "PL"),
    ("Interest on Term Loan", "Finance Cost", "PL"), ("Income Tax", "Tax", "PL"),
    ("Plant & Machinery", "Fixed Assets", "BS"), ("Accumulated Depreciation", "Fixed Assets", "BS"),
    ("Inventories", "Inventory", "BS"), ("Sundry Debtors", "Receivables", "BS"), (BANK, "Cash & Bank", "BS"),
    ("Input GST", "Other Current Assets", "BS"), ("Sundry Creditors", "Payables", "BS"), ("Output GST", "Statutory Dues", "BS"),
    ("TDS Payable", "Statutory Dues", "BS"), ("Provision for Tax", "Statutory Dues", "BS"),
    ("Term Loan - SBI", "Borrowings", "BS"), ("Share Capital", "Share Capital", "BS"),
    ("Reserves & Surplus (Opening)", "Share Capital", "BS"),
]

rows: list[dict] = []
seq: dict[str, int] = {}


def r2(x: float) -> float:
    return float(round(x, 2))


def vno(prefix: str) -> str:
    seq[prefix] = seq.get(prefix, 0) + 1
    return f"{prefix}/2026-27/{seq[prefix]:04d}"


def post(d: date, vtype: str, prefix: str, lines: list[tuple], narr: str, cc: str = "HO") -> str:
    """lines = [(account, party, debit, credit)]; asserts the voucher balances to the paisa."""
    lines = [(a, p, r2(dr), r2(cr)) for a, p, dr, cr in lines]
    dr, cr = round(sum(x[2] for x in lines), 2), round(sum(x[3] for x in lines), 2)
    assert abs(dr - cr) < 0.005, f"unbalanced {narr}: {dr} vs {cr}"
    no = vno(prefix)
    for a, p, d_, c_ in lines:
        rows.append(dict(date=pd.Timestamp(d), voucher_no=no, voucher_type=vtype, account=a, party=p,
                         debit=d_, credit=c_, cost_center=cc, narration=narr))
    return no


def amt(base: float, spread: float = 0.08) -> float:
    return round(base * (1 + rng.uniform(-spread, spread)), 0)


def month_end(p: pd.Period) -> date:
    return p.end_time.date()


def generate(pads: dict | None = None) -> pd.DataFrame:
    """pads = {month_number: [2 or 3, ...]} travel claims posted inside the month (before the tax JV)."""
    pads = pads or {}
    rows.clear(); seq.clear()
    # ------------------------------------------------------------ opening balances (01-Apr-2026)
    opening_debtors = {"Annapurna Retail LLP": 3_100_000, "Bharat Wholesale Co": 2_650_000, "City Mart Stores": 1_900_000,
                       "Deccan Food Distributors": 2_150_000, "Eastern Supply Chain Ltd": 2_200_000}          # 1.20 Cr
    opening_creditors = {"Krishna Agro Commodities": 3_800_000, "Sunrise Packaging Industries": 1_900_000,
                         "Pune Chemicals & Additives": 1_300_000}                                             # 0.70 Cr
    gross_block, acc_dep, inventory, bank = 40_000_000, 12_000_000, 6_000_000, 25_000_000
    out_gst_open, tds_open, loan, share_cap = 600_000, 50_000, 15_000_000, 10_000_000
    assets = gross_block - acc_dep + inventory + sum(opening_debtors.values()) + bank
    liabs = out_gst_open + tds_open + sum(opening_creditors.values()) + loan
    reserves = assets - liabs - share_cap
    od = date(2026, 4, 1)
    lines = [("Plant & Machinery", "", gross_block, 0), ("Accumulated Depreciation", "", 0, acc_dep),
             ("Inventories", "", inventory, 0), (BANK, "", bank, 0)]
    lines += [("Sundry Debtors", c, v, 0) for c, v in opening_debtors.items()]
    lines += [("Sundry Creditors", v, 0, a) for v, a in opening_creditors.items()]
    lines += [("Output GST", "", 0, out_gst_open), ("TDS Payable", "", 0, tds_open), ("Term Loan - SBI", "State Bank of India", 0, loan),
              ("Share Capital", "", 0, share_cap), ("Reserves & Surplus (Opening)", "", 0, reserves)]
    post(od, "Journal", "JV", lines, "Opening balances FY 2026-27")

    # open items for receipts/payments: (due_date, party, amount)
    ar = [(od + timedelta(days=CUSTOMERS[c][0] // 2 + CUSTOMERS[c][1] - 10 if c != "Deccan Food Distributors" else 40),
           c, v) for c, v in opening_debtors.items()]
    ap = [(od + timedelta(days=12 + 6 * i), v, a) for i, (v, a) in enumerate(opening_creditors.items())]
    tds_due_prev, gst_due_prev = tds_open, out_gst_open
    in_gst_bal = 0.0
    capex_done = False
    new_loan = 0

    for m in MONTHS:
        s = SEASON[m.month]
        me = month_end(m)
        d = lambda day: date(m.year, m.month, min(day, me.day))  # noqa: E731
        out_gst = in_gst = tds = 0.0

        # ---- statutory payments for the previous month
        if tds_due_prev:
            post(d(7), "Payment", "PY", [("TDS Payable", "Income Tax Dept", tds_due_prev, 0), (BANK, "", 0, tds_due_prev)],
                 f"TDS deposited for {(m - 1).strftime('%b-%Y')}")
        if gst_due_prev:
            setoff = min(in_gst_bal, gst_due_prev)
            net = r2(gst_due_prev - setoff)
            lines = [("Output GST", "", gst_due_prev, 0)]
            if setoff:
                lines.append(("Input GST", "", 0, setoff))
            lines.append((BANK, "", 0, net))
            post(d(20), "Payment", "PY", lines, f"GSTR-3B {(m - 1).strftime('%b-%Y')}: output GST less ITC paid")
            in_gst_bal -= setoff

        # ---- domestic sales (5 invoices) and one export invoice
        dom_total = 13_000_000 * s
        for i, (c, (days, delay, share)) in enumerate(CUSTOMERS.items()):
            base = amt(dom_total * share, 0.06)
            gst = r2(base * 0.18)
            dt = d(4 + i * 5)
            post(dt, "Sales", "SL", [("Sundry Debtors", c, base + gst, 0), ("Sales - Domestic", "", 0, base), ("Output GST", "", 0, gst)],
                 f"Tax invoice to {c}", "Plant-1")
            ar.append((dt + timedelta(days=days + delay), c, r2(base + gst)))
            out_gst += gst
        exp = amt(2_000_000 * s, 0.05)
        dt = d(26)
        post(dt, "Sales", "SL", [("Sundry Debtors", EXPORT_CUSTOMER[0], exp, 0), ("Sales - Export", "", 0, exp)],
             "Export invoice under LUT (zero-rated)", "Plant-1")
        ar.append((dt + timedelta(days=EXPORT_CUSTOMER[1]), EXPORT_CUSTOMER[0], exp))

        # ---- raw-material purchases (3) + freight (1)
        rm_total = 7_800_000 * s
        for i, (v, days) in enumerate(VENDORS.items()):
            base = amt(rm_total * [0.6, 0.25, 0.15][i], 0.05)
            gst = r2(base * 0.18)
            dt = d(3 + i * 8)
            post(dt, "Purchase", "PU", [("Purchases - Raw Material", "", base, 0), ("Input GST", "", gst, 0),
                                        ("Sundry Creditors", v, 0, base + gst)], f"Purchase bill from {v}", "Plant-1")
            ap.append((dt + timedelta(days=days), v, r2(base + gst)))
            in_gst += gst
        base = amt(300_000 * s, 0.05)
        gst = r2(base * 0.18)
        dt = d(15)
        post(dt, "Purchase", "PU", [("Freight Inward", "", base, 0), ("Input GST", "", gst, 0),
                                    ("Sundry Creditors", FREIGHT_VENDOR, 0, base + gst)], "Inward freight bill", "Plant-1")
        ap.append((dt + timedelta(days=30), FREIGHT_VENDOR, r2(base + gst)))
        in_gst += gst

        # ---- customer receipts / vendor payments falling due this month (FIFO by due date)
        for due, c, a in sorted([x for x in ar if x[0] <= me]):
            post(max(due, d(1)), "Receipt", "RC", [(BANK, "", a, 0), ("Sundry Debtors", c, 0, a)], f"Receipt from {c}")
        ar = [x for x in ar if x[0] > me]
        for due, v, a in sorted([x for x in ap if x[0] <= me]):
            post(max(due, d(1)), "Payment", "PY", [("Sundry Creditors", v, a, 0), (BANK, "", 0, a)], f"Payment to {v}")
        ap = [x for x in ap if x[0] > me]

        # ---- payroll and overheads
        sal, welf = amt(1_600_000, 0.02), amt(120_000, 0.15)
        post(d(30), "Payment", "PY", [("Salaries & Wages", "", sal, 0), ("Staff Welfare", "", welf, 0), (BANK, "", 0, sal + welf)],
             f"Salary and staff welfare {m.strftime('%b-%Y')}")
        rent = 300_000
        post(d(5), "Payment", "PY", [("Rent", "Prime Estates", rent, 0), ("TDS Payable", "", 0, rent * 0.10), (BANK, "", 0, rent * 0.90)],
             "Factory rent (TDS 194-I @10%)")
        tds += rent * 0.10
        elec = amt(450_000 * s, 0.07)
        post(d(12), "Payment", "PY", [("Electricity", "MSEDCL", elec, 0), (BANK, "", 0, elec)], "Electricity bill", "Plant-1")
        prof = 75_000
        post(d(18), "Payment", "PY", [("Professional Fees", "Mehta & Co LLP", prof, 0), ("TDS Payable", "", 0, prof * 0.10),
                                      (BANK, "", 0, prof * 0.90)], "Audit/advisory retainer (TDS 194J @10%)")
        tds += prof * 0.10
        if m.month == 8:  # PLANTED: one-off spike
            spike = 650_000
            post(d(22), "Payment", "PY", [("Professional Fees", "Vertex Consulting", spike, 0), ("TDS Payable", "", 0, spike * 0.10),
                                          (BANK, "", 0, spike * 0.90)], "Consultancy - ERP process study (TDS 194J @10%)")
            tds += spike * 0.10
        adv = amt(350_000 * s, 0.10)
        post(d(16), "Payment", "PY", [("Advertising", "", adv, 0), (BANK, "", 0, adv)], "Trade promotion and digital ads")
        trav = amt(120_000, 0.15)
        post(d(27), "Payment", "PY", [("Travel & Conveyance", "", trav, 0), (BANK, "", 0, trav)], "Sales team travel reimbursement")

        # ---- capex (Jul) and PLANTED duplicate payment (Jul)
        if m.month == 7 and not capex_done:
            cap = 4_000_000
            gst = cap * 0.18
            post(d(10), "Purchase", "PU", [("Plant & Machinery", "", cap, 0), ("Input GST", "", gst, 0),
                                           ("Sundry Creditors", "Precision Machines Ltd", 0, cap + gst)], "New packing line (capex)", "Plant-1")
            post(d(25), "Payment", "PY", [("Sundry Creditors", "Precision Machines Ltd", cap + gst, 0),
                                          ("Term Loan - SBI", "State Bank of India", 0, cap), (BANK, "", 0, gst)],
                 "Packing line paid: SBI term loan disbursed direct to vendor; GST from own funds")
            new_loan = cap  # interest from next month's EMI
            in_gst += gst
            gross_block += cap
            capex_done = True
        if m.month == 7:
            dup = 1_150_000
            for day in (21, 23):  # same vendor, same amount, 2 days apart
                post(d(day), "Payment", "PY", [("Sundry Creditors", "Sunrise Packaging Industries", dup, 0), (BANK, "", 0, dup)],
                     "Advance to Sunrise Packaging Industries")

        # ---- finance items
        intr = r2(loan * 0.095 / 12)
        post(d(5), "Payment", "PY", [("Interest on Term Loan", "State Bank of India", intr, 0),
                                     ("Term Loan - SBI", "State Bank of India", 500_000, 0), (BANK, "", 0, intr + 500_000)],
             "Term loan EMI: interest @9.5% + principal Rs 5 L")
        loan -= 500_000
        if m.month == 7 and capex_done:
            loan += new_loan
        ii = amt(30_000, 0.1)
        post(me, "Receipt", "RC", [(BANK, "", ii, 0), ("Interest Income", "", 0, ii)], "Interest on sweep FD")

        # ---- travel reimbursements (2-line; 3-line claim includes meals)
        for j, size in enumerate(pads.get(m.month, [])):
            a1 = amt(25_000, 0.2)
            if size == 3:
                a2 = amt(6_000, 0.3)
                post(d(9 + 7 * j), "Payment", "PY", [("Travel & Conveyance", "", a1, 0), ("Staff Welfare", "", a2, 0), (BANK, "", 0, a1 + a2)],
                     "Employee expense claim (travel + meals)")
            else:
                post(d(9 + 7 * j), "Payment", "PY", [("Travel & Conveyance", "", a1, 0), (BANK, "", 0, a1)], "Local conveyance reimbursement")

        # ---- month-end JVs: depreciation, inventory change, tax provision
        dep = r2((gross_block - (4_000_000 if m.month <= 7 and capex_done else 0)) * 0.10 / 12)
        post(me, "Journal", "JV", [("Depreciation", "", dep, 0), ("Accumulated Depreciation", "", 0, dep)], "Depreciation SLM 10% p.a.")
        chg = float(rng.choice([-1, 1])) * amt(180_000, 0.3)
        lines = [("Inventories", "", chg, 0), ("Changes in Inventories", "", 0, chg)] if chg > 0 else \
                [("Changes in Inventories", "", -chg, 0), ("Inventories", "", 0, -chg)]
        post(me, "Journal", "JV", lines, "Closing stock adjustment (physical count)", "Plant-1")

        df = pd.DataFrame(rows)
        mm = df[df["date"].dt.to_period("M") == m]
        cat = dict((a, c) for a, c, _ in MAPPING)
        pl = mm[mm["account"].map(lambda a: cat.get(a) not in (None, "Tax") and dict((x, z) for x, _, z in MAPPING)[a] == "PL")]
        pbt = float((pl["credit"] - pl["debit"]).sum())
        tax = r2(max(pbt, 0) * TAX_RATE)
        post(me, "Journal", "JV", [("Income Tax", "", tax, 0), ("Provision for Tax", "", 0, tax)], "Provision for income tax @25.168% (115BAA)")
        if m.month in (6, 9):  # advance tax instalments: pay the provision to date
            prov = df[df["account"] == "Provision for Tax"]
            due = r2(float((prov["credit"] - prov["debit"]).sum()) + tax)
            post(d(15), "Payment", "PY", [("Provision for Tax", "Income Tax Dept", due, 0), (BANK, "", 0, due)], "Advance tax instalment")

        in_gst_bal += in_gst
        gst_due_prev, tds_due_prev = r2(out_gst), r2(tds)

    return pd.DataFrame(rows).sort_values(["date", "voucher_no"], kind="stable").reset_index(drop=True)


def budget() -> pd.DataFrame:
    out = []
    for m in MONTHS:
        s, key = SEASON[m.month], m.strftime("%Y-%m")
        dep = 4_000_000 * 0.10 / 12 + (4_000_000 * 0.10 / 12 if m.month >= 8 else 0) + 36_000_000 * 0.10 / 12
        out += [
            (key, "Revenue", round(13_600_000 * s), "Domestic sales"),
            (key, "Revenue", round(2_100_000 * s), "Export sales"),
            (key, "COGS", round(8_050_000 * s), "Raw material, freight, stock change"),
            (key, "Employee Cost", 1_700_000, "Salaries and staff welfare"),
            (key, "Admin Expenses", round(800_000 * s), "Rent, power, professional fees"),
            (key, "Marketing Expenses", round(450_000 * s), "Advertising and travel"),
            (key, "Depreciation", round(dep, 2), "SLM 10% incl. new packing line from Aug"),
            (key, "Finance Cost", round(115_000), "Term loan interest"),
            (key, "Other Income", 30_000, "Interest on sweep FD"),
            (key, "Tax", round(850_000 * s), "Income tax @25.168%"),
        ]
    return pd.DataFrame(out, columns=["month", "category", "amount", "budget_line"])


def control_totals(gl: pd.DataFrame, bud: pd.DataFrame) -> pd.DataFrame:
    cat = {a: c for a, c, _ in MAPPING}
    stm = {a: s for a, _, s in MAPPING}
    g = gl.assign(category=gl.account.map(cat), statement=gl.account.map(stm), month=gl.date.dt.strftime("%Y-%m"),
                  net_cr=gl.credit - gl.debit)
    pl = g[g.statement == "PL"].pivot_table(index="category", columns="month", values="net_cr", aggfunc="sum", fill_value=0)
    gv = lambda c: pl.loc[c] if c in pl.index else 0  # noqa: E731
    t = pd.DataFrame({
        "Revenue": gv("Revenue"), "COGS": -gv("COGS"), "Gross Profit": gv("Revenue") + gv("COGS"),
        "Employee Cost": -gv("Employee Cost"), "Admin Expenses": -gv("Admin Expenses"), "Marketing Expenses": -gv("Marketing Expenses"),
    }).T
    t.loc["EBITDA"] = t.loc["Gross Profit"] - t.loc["Employee Cost"] - t.loc["Admin Expenses"] - t.loc["Marketing Expenses"]
    t.loc["Depreciation"] = -gv("Depreciation")
    t.loc["Finance Cost"] = -gv("Finance Cost")
    t.loc["Other Income"] = gv("Other Income")
    t.loc["PBT"] = t.loc["EBITDA"] - t.loc["Depreciation"] - t.loc["Finance Cost"] + t.loc["Other Income"]
    t.loc["Tax"] = -gv("Tax")
    t.loc["PAT"] = t.loc["PBT"] - t.loc["Tax"]
    bankc = g[g.account == BANK].groupby("month").apply(lambda x: (x.debit - x.credit).sum()).cumsum()
    t.loc["Closing Bank (HDFC)"] = bankc
    t.loc["Budget Revenue"] = bud[bud.category == "Revenue"].groupby("month").amount.sum()
    t["H1 Total"] = t.drop(index=["Closing Bank (HDFC)"]).sum(axis=1)
    t.loc["Closing Bank (HDFC)", "H1 Total"] = t.loc["Closing Bank (HDFC)", "2026-09"]
    return t.round(2)


def main() -> int:
    base = len(generate())                      # pass 1: count lines without reimbursements
    deficit = TARGET_GL - base
    if deficit < 2:
        raise SystemExit(f"Base design has {base} lines; need at least 2 below {TARGET_GL}.")
    sizes = [3] if deficit % 2 else []
    sizes += [2] * ((deficit - sum(sizes)) // 2)
    pads: dict = {}
    for i, sz in enumerate(sizes):
        pads.setdefault(MONTHS[i % len(MONTHS)].month, []).append(sz)
    global rng
    rng = np.random.default_rng(2026)          # pass 2: identical amounts, reimbursements inside each month
    gl = generate(pads)
    bud = budget()
    # ------------------------------------------------ integrity checks (fail loudly)
    assert len(gl) == TARGET_GL, len(gl)
    assert len(bud) == TARGET_BUD, len(bud)
    vb = gl.groupby("voucher_no")[["debit", "credit"]].sum().round(2)
    assert (vb.debit == vb.credit).all(), vb[vb.debit != vb.credit]
    assert round(gl.debit.sum(), 2) == round(gl.credit.sum(), 2)
    assert set(gl.account) <= {a for a, _, _ in MAPPING}, set(gl.account) - {a for a, _, _ in MAPPING}
    daily = gl[gl.account == BANK].assign(n=lambda x: x.debit - x.credit).groupby("date").n.sum().cumsum()
    assert daily.min() > 0, f"bank goes negative: {daily.min()}"
    assert not (gl[["debit", "credit"]] < 0).any().any()

    mapping = pd.DataFrame(MAPPING, columns=["account", "category", "statement"])
    path = ROOT / "input" / "MIS_Input_Test_500_Lines.xlsx"
    build(path, gl[[c[0] for c in GL_COLS]], bud, mapping, "MIS Input: TEST DATA (synthetic) Apr-2026 to Sep-2026")

    ct = control_totals(gl, bud)
    wb = load_workbook(path)
    ws = wb.create_sheet("Control_Totals", index=4)
    ws["A1"] = "Control totals (answer key) – computed independently from the GL sheet. Tool output must match these."
    ws["A1"].font = Font(bold=True, color=NAVY, size=12)
    hdr = ["Line item (INR)"] + list(ct.columns)
    for j, h in enumerate(hdr, 1):
        c = ws.cell(row=3, column=j, value=h)
        c.font, c.fill, c.alignment = HDR_FONT, HDR_FILL, Alignment(horizontal="center")
    for i, (idx, row) in enumerate(ct.iterrows(), 4):
        ws.cell(row=i, column=1, value=idx).font = Font(bold=idx in ("Revenue", "EBITDA", "PBT", "PAT"))
        for j, v in enumerate(row, 2):
            c = ws.cell(row=i, column=j, value=float(v))
            c.number_format = "#,##,##0.00"
    r = 4 + len(ct) + 1
    notes = [
        ("GL lines", len(gl)), ("Vouchers", gl.voucher_no.nunique()), ("Ledgers used", gl.account.nunique()),
        ("Total debit = total credit", round(gl.debit.sum(), 2)), ("Budget lines", len(bud)),
        ("Planted test 1", "Duplicate payment: Sunrise Packaging Industries Rs 11,50,000 on 21-Jul and 23-Jul-2026"),
        ("Planted test 2", "Expense spike: Professional Fees Rs 6,50,000 (Vertex Consulting) on 22-Aug-2026"),
        ("Planted test 3", "Slow payer: Deccan Food Distributors invoices unpaid beyond due date (overdue ageing)"),
        ("Budget sheet note", "Revenue has 2 rows per month (domestic + export); the tool adds them. Column 'budget_line' is a description only."),
    ]
    for k, (a, b) in enumerate(notes):
        ws.cell(row=r + k, column=1, value=a).font = Font(bold=True)
        c = ws.cell(row=r + k, column=2, value=b)
        if isinstance(b, float):
            c.number_format = "#,##,##0.00"
    ws.column_dimensions["A"].width = 30
    for col in "BCDEFGH":
        ws.column_dimensions[col].width = 17
    wsb = wb["Budget"]
    wsb.cell(row=1, column=4, value="budget_line").font = HDR_FONT
    wsb.cell(row=1, column=4).fill = HDR_FILL
    for i, v in enumerate(bud.budget_line, 2):
        wsb.cell(row=i, column=4, value=v)
    wsb.column_dimensions["D"].width = 40
    wb.save(path)
    print(f"written {path}\nGL lines {len(gl)} | vouchers {gl.voucher_no.nunique()} | Dr {gl.debit.sum():,.2f} = Cr {gl.credit.sum():,.2f} | budget lines {len(bud)}")
    print(ct.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
