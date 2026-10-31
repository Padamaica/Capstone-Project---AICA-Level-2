"""End-to-end orchestration: ingest -> validate -> compute -> store -> commentary -> reports."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import settings
from .engine import (ageing, balance_sheet_monthly, budget_vs_actual, cash_flow_monthly, detect_anomalies, enrich,
                     forecast_pnl, pnl_monthly, ratios_monthly)
from .ingestion import ValidationReport, load_budget, load_coa_mapping, load_gl, validate_gl
from .localisation import enable_outbound_guard
from .storage import audit, save_results


@dataclass
class MISResult:
    month: str
    egl: pd.DataFrame
    pnl: pd.DataFrame
    balance_sheet: pd.DataFrame
    cash_flow: pd.DataFrame
    ratios: pd.DataFrame
    bva_month: pd.DataFrame | None
    bva_ytd: pd.DataFrame | None
    ar_detail: pd.DataFrame
    ar_summary: pd.DataFrame
    ap_detail: pd.DataFrame
    ap_summary: pd.DataFrame
    anomalies: pd.DataFrame
    forecast: pd.DataFrame | None
    validation: ValidationReport
    commentary: dict = field(default_factory=dict)

    @property
    def months(self) -> list[str]:
        return list(self.pnl.columns)

    @property
    def party_names(self) -> list[str]:
        return sorted(set(self.egl["party"]) - {""})


def run_analysis(gl_src, budget_src=None, mapping_src=None, month: str | None = None, *, gl_name: str | None = None,
                 budget_name: str | None = None, persist: bool = True, with_commentary: bool = True,
                 use_llm: bool = True, user: str = "system", strict: bool = True) -> MISResult:
    if settings.block_outbound_network:
        enable_outbound_guard()

    gl = load_gl(gl_src, gl_name)
    mapping = load_coa_mapping(mapping_src or settings.coa_mapping_path)
    budget = load_budget(budget_src, budget_name) if budget_src is not None else None
    vr = validate_gl(gl, mapping)
    audit("data_loaded", user, rows=len(gl), validation=vr.as_dict())
    if strict and not vr.ok:
        raise ValueError("Data validation failed:\n- " + "\n- ".join(vr.errors))

    egl = enrich(gl, mapping)
    pnl = pnl_monthly(egl)
    month = month or pnl.columns[-1]
    if month not in pnl.columns:
        raise ValueError(f"Month {month} not in data. Available: {list(pnl.columns)}")
    # analyse "as of" the selected month (no look-ahead)
    egl_asof = egl[egl["month"] <= month]
    pnl = pnl.loc[:, [c for c in pnl.columns if c <= month]]
    bs = balance_sheet_monthly(egl_asof, pnl)
    cf = cash_flow_monthly(egl_asof, pnl, bs)
    ratios = ratios_monthly(pnl, bs)
    month_end = pd.Period(month, freq="M").end_time.normalize()
    ar_d, ar_s = ageing(egl_asof, month_end, "AR")
    ap_d, ap_s = ageing(egl_asof, month_end, "AP")
    bva_m = bva_y = None
    if budget is not None:
        bva_m = budget_vs_actual(pnl, budget, month, False, settings.fy_start_month, settings.variance_threshold_pct)
        bva_y = budget_vs_actual(pnl, budget, month, True, settings.fy_start_month, settings.variance_threshold_pct)
    anomalies = detect_anomalies(egl_asof, settings.anomaly_z_threshold, settings.duplicate_window_days)
    try:
        fc = forecast_pnl(pnl, 3)
    except ValueError:
        fc = None

    res = MISResult(month, egl_asof, pnl, bs, cf, ratios, bva_m, bva_y, ar_d, ar_s, ap_d, ap_s, anomalies, fc, vr)
    if persist:
        save_results(egl_asof, budget, pnl, bs, ar_d, ap_d)
    if with_commentary:
        from .ai.commentary import generate_commentary
        res.commentary = generate_commentary(res, use_llm=use_llm)
    audit("analysis_run", user, month=month, anomalies=len(anomalies), commentary_source=res.commentary.get("source"))
    return res


def generate_reports(res: MISResult, out_dir: Path | None = None, user: str = "system") -> dict[str, Path]:
    from .reports.excel_mis import build_excel_mis
    from .reports.pdf_mis import build_pdf_mis

    out_dir = Path(out_dir or settings.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"MIS_{res.month}"
    paths = {"excel": build_excel_mis(res, out_dir / f"{stem}.xlsx"), "pdf": build_pdf_mis(res, out_dir / f"{stem}.pdf")}
    audit("reports_generated", user, month=res.month, files=[str(p) for p in paths.values()])
    return paths
