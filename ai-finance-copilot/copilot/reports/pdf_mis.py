"""Board-pack PDF (reportlab + matplotlib). Uses the DejaVuSans font bundled with matplotlib so ₹ renders."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,  # noqa: E402
                                TableStyle)

from ..config import settings  # noqa: E402
from ..engine.statements import ytd_columns  # noqa: E402
from ..utils import fmt_inr, month_label  # noqa: E402

NAVY = colors.HexColor("#1F3864")


def _fonts() -> tuple[str, str]:
    try:
        base = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        pdfmetrics.registerFont(TTFont("DejaVu", str(base / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(base / "DejaVuSans-Bold.ttf")))
        return "DejaVu", "DejaVu-Bold"
    except Exception:  # noqa: BLE001
        return "Helvetica", "Helvetica-Bold"


def _md_inline(s: str) -> str:
    s = escape(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def _table(data: list[list], col_widths=None, font="DejaVu", bold="DejaVu-Bold", zebra=True, highlight_rows=()) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("FONT", (0, 0), (-1, -1), font, 7.5), ("FONT", (0, 0), (-1, 0), bold, 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BFBFBF")),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for i in range(1, len(data)):
        if zebra and i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F2F2F2")))
    for i in highlight_rows:
        style += [("FONT", (0, i), (-1, i), bold, 7.5), ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#D9E1F2"))]
    t.setStyle(TableStyle(style))
    return t


def _chart(res, tmp: Path) -> Path:
    months = res.months[-12:]
    labels = [pd.Period(x, freq="M").strftime("%b-%y") for x in months]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.4), dpi=150)
    a1.bar(labels, res.pnl.loc["Revenue", months] / 1e5, color="#8EA9DB", label="Revenue")
    a1.plot(labels, res.pnl.loc["EBITDA", months] / 1e5, color="#1F3864", marker="o", label="EBITDA")
    a1.plot(labels, res.pnl.loc["PAT", months] / 1e5, color="#C55A11", marker="s", label="PAT")
    if res.forecast is not None:
        fl = [pd.Period(x, freq="M").strftime("%b-%y") for x in res.forecast.columns]
        a1.bar(fl, res.forecast.loc["Revenue"] / 1e5, color="#D9E1F2", edgecolor="#8EA9DB", hatch="//", label="Forecast")
    a1.set_title("Revenue / EBITDA / PAT (₹ lakh)", fontsize=9)
    a1.legend(fontsize=7)
    a1.tick_params(axis="x", rotation=60, labelsize=7)
    a1.tick_params(axis="y", labelsize=7)
    a2.plot(labels, res.ratios.loc["Cash & Bank", months] / 1e5, color="#548235", marker="o", label="Closing cash (₹ L)")
    a2b = a2.twinx()
    a2b.plot(labels, res.ratios.loc["DSO (days)", months], color="#C00000", ls="--", label="DSO (days)")
    a2.set_title("Cash & DSO", fontsize=9)
    a2.tick_params(axis="x", rotation=60, labelsize=7)
    a2.tick_params(axis="y", labelsize=7)
    a2b.tick_params(axis="y", labelsize=7)
    h1, l1 = a2.get_legend_handles_labels()
    h2, l2 = a2b.get_legend_handles_labels()
    a2.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left")
    for ax in (a1, a2):
        ax.spines[["top"]].set_visible(False)
    fig.tight_layout()
    out = tmp / "chart.png"
    fig.savefig(out)
    plt.close(fig)
    return out


def build_pdf_mis(res, path: Path) -> Path:
    font, bold = _fonts()
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Title"], fontName=bold, fontSize=16, textColor=NAVY, alignment=0, spaceAfter=2)
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName=bold, fontSize=11, textColor=NAVY, spaceBefore=8, spaceAfter=4)
    H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontName=bold, fontSize=9.5, textColor=NAVY, spaceBefore=5, spaceAfter=2)
    BODY = ParagraphStyle("B", parent=ss["BodyText"], fontName=font, fontSize=8.5, leading=11.5)
    BUL = ParagraphStyle("BL", parent=BODY, leftIndent=10, bulletIndent=2)
    SMALL = ParagraphStyle("S", parent=BODY, fontSize=7, textColor=colors.grey)

    m, months = res.month, res.months
    prev = months[-2] if len(months) > 1 else m
    ytd = ytd_columns(months, m, settings.fy_start_month)
    story = [Paragraph(f"{escape(settings.company_name)}: MIS Board Pack", H1),
             Paragraph(f"Period: {month_label(m)} &nbsp;|&nbsp; YTD: {month_label(ytd[0])} to {month_label(ytd[-1])} &nbsp;|&nbsp; "
                       f"Commentary source: {escape(str(res.commentary.get('source', 'n/a')))}", SMALL), Spacer(1, 6)]

    # KPI strip
    def k(line):
        return float(res.pnl.loc[line, m]), float(res.pnl.loc[line, prev])
    cells = []
    for line in ["Revenue", "EBITDA", "PAT"]:
        cur, pv = k(line)
        ch = (cur - pv) / abs(pv) * 100 if pv else 0
        cells.append(f"<b>{line}</b><br/>{fmt_inr(cur)}<br/><font size=7 color='{'#548235' if ch >= 0 else '#C00000'}'>{ch:+.1f}% MoM</font>")
    cells.append(f"<b>Cash</b><br/>{fmt_inr(float(res.ratios.loc['Cash & Bank', m]))}<br/><font size=7>DSO {res.ratios.loc['DSO (days)', m]:.0f}d</font>")
    cells.append(f"<b>Anomalies</b><br/>{len(res.anomalies)}<br/><font size=7>to review</font>")
    kp = Table([[Paragraph(c, ParagraphStyle('k', parent=BODY, alignment=1, fontSize=10, leading=13)) for c in cells]],
               colWidths=[3.6 * cm] * 5)
    kp.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, NAVY), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFBFBF")),
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F6FC")), ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [kp, Spacer(1, 6)]

    with tempfile.TemporaryDirectory() as td:
        story.append(Image(str(_chart(res, Path(td))), width=18 * cm, height=5.6 * cm))

        story.append(Paragraph("Management Commentary", H2))
        for line in (res.commentary.get("text") or "").splitlines():
            line = line.rstrip()
            if not line:
                continue
            if line.startswith("#"):
                story.append(Paragraph(_md_inline(line.lstrip("# ")), H3))
            elif line.lstrip().startswith(("- ", "* ")):
                story.append(Paragraph(_md_inline(line.lstrip()[2:]), BUL, bulletText="•"))
            else:
                story.append(Paragraph(_md_inline(line), BODY))
        if res.commentary.get("unverified_numbers"):
            story.append(Paragraph(f"⚠ Numbers not verified against source: {', '.join(res.commentary['unverified_numbers'])}", SMALL))

        story.append(PageBreak())
        # P&L table (last 3 months + YTD)
        story.append(Paragraph("Profit & Loss (₹ lakh)", H2))
        cols = months[-3:]
        hdr = ["Particulars"] + [month_label(c) for c in cols] + ["YTD"]
        data = [hdr]
        hl = []
        for i, line in enumerate(res.pnl.index, start=1):
            vals = [res.pnl.loc[line, c] / 1e5 for c in cols] + [res.pnl.loc[line, ytd].sum() / 1e5]
            data.append([line] + [f"{v:,.2f}" for v in vals])
            if line in ("Gross Profit", "EBITDA", "EBIT", "PBT", "PAT"):
                hl.append(i)
        story.append(_table(data, [5 * cm] + [3 * cm] * 4, font, bold, highlight_rows=hl))

        if res.bva_month is not None:
            story.append(Paragraph(f"Budget vs Actual: {month_label(m)} (₹ lakh)", H2))
            data = [["Line item", "Budget", "Actual", "Variance", "Var %", "Status"]]
            st = []
            for i, x in enumerate(res.bva_month.itertuples(), start=1):
                data.append([x.line_item, f"{x.budget / 1e5:,.2f}", f"{x.actual / 1e5:,.2f}", f"{x.variance / 1e5:,.2f}",
                             "-" if pd.isna(x.variance_pct) else f"{x.variance_pct:+.1f}%", x.status + (" ⚑" if x.flag else "")])
                st.append(("TEXTCOLOR", (5, i), (5, i), colors.HexColor("#548235") if x.status == "Favourable" else colors.HexColor("#C00000")))
            t = _table(data, [4.5 * cm, 2.6 * cm, 2.6 * cm, 2.6 * cm, 2 * cm, 2.7 * cm], font, bold)
            t.setStyle(TableStyle(st))
            story.append(t)

        story.append(Paragraph("Receivables Ageing (₹ lakh)", H2))
        s = res.ar_summary
        data = [list(map(str, s.columns))] + [[r[0]] + [f"{v / 1e5:,.2f}" for v in r[1:]] for r in s.itertuples(index=False)]
        story.append(_table(data, [4.5 * cm] + [2.2 * cm] * (len(s.columns) - 1), font, bold, highlight_rows=[len(data) - 1]))

        if not res.anomalies.empty:
            story.append(Paragraph("Anomalies & Control Exceptions", H2))
            cell = ParagraphStyle("c", parent=BODY, fontSize=7, leading=9)
            data = [["Type", "Sev.", "Date", "Account / Party", "Amount", "Detail"]]
            for a in res.anomalies.head(15).itertuples():
                data.append([Paragraph(escape(a.type), cell), a.severity, str(a.date),
                             Paragraph(escape(f"{a.account} / {a.party or '-'}"), cell), fmt_inr(a.amount), Paragraph(escape(a.detail), cell)])
            story.append(KeepTogether(_table(data, [3 * cm, 1.2 * cm, 1.8 * cm, 3.8 * cm, 2 * cm, 5.2 * cm], font, bold)))

        story.append(Spacer(1, 10))
        story.append(Paragraph("Generated by AI Finance Co-Pilot. All figures are computed deterministically from the ledger; "
                               "AI is used only for narrative. Data processed locally (no external transfer).", SMALL))

        def _footer(canvas, doc):
            canvas.saveState()
            canvas.setFont(font, 7)
            canvas.setFillColor(colors.grey)
            canvas.drawString(1.5 * cm, 1 * cm, f"{settings.company_name} | MIS {month_label(m)} | Confidential")
            canvas.drawRightString(A4[0] - 1.5 * cm, 1 * cm, f"Page {doc.page}")
            canvas.restoreState()

        path = Path(path)
        doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.3 * cm,
                                bottomMargin=1.6 * cm, title=f"MIS {month_label(m)}", author="AI Finance Co-Pilot")
        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path
