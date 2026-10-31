"""FastAPI backend: REST API for integrations (ERP push, scheduler, React front-end, Power BI).

Run:  uvicorn api.main:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs     Auth: header  X-API-Key: <COPILOT_API_KEYS>
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copilot.ai import ask, get_llm  # noqa: E402
from copilot.config import ROOT, settings  # noqa: E402
from copilot.localisation import enable_outbound_guard  # noqa: E402
from copilot.pipeline import MISResult, generate_reports, run_analysis  # noqa: E402
from copilot.storage import audit  # noqa: E402

if settings.block_outbound_network:
    enable_outbound_guard()

app = FastAPI(title="AI Finance Co-Pilot API", version="0.1.0",
              description="MIS automation, financial analysis and reporting. Self-hosted; data stays local.")
STATE: dict[str, MISResult] = {}
UPLOADS = settings.data_dir / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)


def require_key(x_api_key: str = Header(default="")) -> str:
    if x_api_key not in settings.api_keys:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return f"key:{x_api_key[:4]}***"


@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    audit("http_request", request.headers.get("x-api-key", "")[:4] + "***", method=request.method, path=request.url.path,
          status=response.status_code, ms=round((time.time() - t0) * 1000), client=request.client.host if request.client else None)
    return response


def _df(df):
    if df is None:
        return None
    return json.loads(df.to_json(orient="split", date_format="iso"))


def _res() -> MISResult:
    if "latest" not in STATE:
        raise HTTPException(status_code=404, detail="No analysis yet. POST /analyze/sample or /upload first.")
    return STATE["latest"]


def _summary(res: MISResult) -> dict:
    return {"month": res.month, "months": res.months, "validation": res.validation.as_dict(),
            "anomalies": int(len(res.anomalies)), "commentary_source": res.commentary.get("source")}


@app.get("/health")
def health():
    llm = get_llm()
    return {"status": "ok", "llm_provider": settings.llm_provider, "llm_model": settings.llm_model,
            "llm_healthy": bool(llm and llm.health()), "outbound_guard": settings.block_outbound_network,
            "pii_masking": settings.mask_pii_before_llm}


@app.post("/analyze/sample")
def analyze_sample(month: Optional[str] = None, use_llm: bool = True, user: str = Depends(require_key)):
    res = run_analysis(ROOT / "data/sample/gl.csv", ROOT / "data/sample/budget.csv", None, month, use_llm=use_llm, user=user)
    STATE["latest"] = res
    return _summary(res)


@app.post("/upload")
def upload(gl: UploadFile = File(...), budget: Optional[UploadFile] = File(None), mapping: Optional[UploadFile] = File(None),
           month: Optional[str] = Form(None), use_llm: bool = Form(True), user: str = Depends(require_key)):
    batch = UPLOADS / uuid.uuid4().hex[:12]
    batch.mkdir(parents=True)
    saved = {}
    for key, f in (("gl", gl), ("budget", budget), ("mapping", mapping)):
        if f is not None and f.filename:
            dest = batch / Path(f.filename).name
            with dest.open("wb") as out:
                shutil.copyfileobj(f.file, out)
            saved[key] = dest
    try:
        res = run_analysis(saved["gl"], saved.get("budget"), saved.get("mapping"), month, use_llm=use_llm, user=user)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    STATE["latest"] = res
    return {"batch": batch.name, **_summary(res)}


@app.get("/pnl")
def pnl(_: str = Depends(require_key)):
    return _df(_res().pnl)


@app.get("/balance-sheet")
def balance_sheet(_: str = Depends(require_key)):
    return _df(_res().balance_sheet)


@app.get("/cash-flow")
def cash_flow(_: str = Depends(require_key)):
    return _df(_res().cash_flow)


@app.get("/ratios")
def ratios(_: str = Depends(require_key)):
    return _df(_res().ratios)


@app.get("/budget-variance")
def budget_variance(ytd: bool = False, _: str = Depends(require_key)):
    r = _res()
    return _df(r.bva_ytd if ytd else r.bva_month)


@app.get("/ageing/{kind}")
def ageing(kind: str, detail: bool = False, _: str = Depends(require_key)):
    r = _res()
    kind = kind.upper()
    if kind not in ("AR", "AP"):
        raise HTTPException(400, "kind must be AR or AP")
    return _df((r.ar_detail if detail else r.ar_summary) if kind == "AR" else (r.ap_detail if detail else r.ap_summary))


@app.get("/anomalies")
def anomalies(_: str = Depends(require_key)):
    return _df(_res().anomalies)


@app.get("/forecast")
def forecast(_: str = Depends(require_key)):
    return _df(_res().forecast)


@app.get("/commentary")
def commentary(_: str = Depends(require_key)):
    c = _res().commentary
    return {k: c.get(k) for k in ("text", "source", "unverified_numbers", "note")}


class AskIn(BaseModel):
    question: str
    use_llm: bool = True


@app.post("/ask")
def ask_endpoint(body: AskIn, user: str = Depends(require_key)):
    r = _res()
    out = ask(body.question, r.party_names, use_llm=body.use_llm)
    audit("ask", user, question=body.question, sql=out.get("sql"), source=out.get("source"))
    return {"answer": out["answer"], "sql": out.get("sql"), "source": out.get("source"), "note": out.get("note"),
            "data": _df(out["data"].head(200)) if out.get("data") is not None else None}


@app.post("/reports")
def reports(user: str = Depends(require_key)):
    paths = generate_reports(_res(), user=user)
    return {k: p.name for k, p in paths.items()}


@app.get("/reports/{fmt}")
def download_report(fmt: str, _: str = Depends(require_key)):
    r = _res()
    ext = {"excel": "xlsx", "xlsx": "xlsx", "pdf": "pdf"}.get(fmt.lower())
    if not ext:
        raise HTTPException(400, "fmt must be excel or pdf")
    path = settings.output_dir / f"MIS_{r.month}.{ext}"
    if not path.exists():
        generate_reports(r)
    return FileResponse(path, filename=path.name)
