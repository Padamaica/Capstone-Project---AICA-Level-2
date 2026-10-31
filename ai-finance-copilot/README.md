# AI Finance Co-Pilot (MVP)

Automates **MIS, financial analysis and reporting** from your ledger, with **full data localisation**:
all data, models and logs stay on your server or in your in-country cloud region.

**Golden rule:** Python calculates every number deterministically. The AI (a self-hosted LLM) only writes the
narrative and answers questions, and a *numeric guard* rejects any narrative containing numbers that were not in the source facts.

---

## What it does

| Module | Output |
|---|---|
| Ingestion | GL / Day Book from **CSV, Excel, Tally XML**. Auto-maps column names from Tally, Zoho, SAP, Busy and others |
| Data validation | Trial balance check, unbalanced vouchers, unmapped ledgers, duplicates, missing months |
| Statements | Monthly **P&L, Balance Sheet, Cash Flow (indirect)**, YTD by Indian FY (Apr–Mar) |
| Analysis | Ratios (margins, DSO/DPO, current ratio, D/E, interest cover), **Budget vs Actual** (month + YTD), **AR/AP ageing (FIFO)** |
| Anomalies | Duplicate payments, expense spikes (robust z-score), unusually large entries |
| Forecast | 3-month revenue (damped Holt + 80% band) and projected P&L |
| AI commentary | CFO-style MIS commentary from a local LLM, with PII masking, numeric guard and a rule-based fallback |
| Ask your data | Natural language → **read-only, validated SQL** → answer |
| Reports | **Excel MIS pack** (11 formatted sheets, charts, Indian lakh/crore format) + **PDF board pack** |
| Automation | CLI, REST API, Streamlit UI, monthly cron job with internal-SMTP email |
| Compliance | Outbound-network guard, endpoint allow-list, PII masking, JSON audit trail, telemetry off |

## Project structure

```
ai-finance-copilot/
├── copilot/                  # core library (no web framework dependency)
│   ├── config.py             # settings from env/.env
│   ├── localisation.py       # endpoint allow-list + outbound socket guard
│   ├── ingestion/            # loaders (CSV/XLSX/Tally XML) + validators
│   ├── engine/               # statements, ratios, variance, ageing, forecast, anomalies
│   ├── ai/                   # llm clients (Ollama / vLLM), commentary, NL→SQL, PII masker
│   ├── reports/              # Excel MIS + PDF board pack
│   ├── storage.py            # SQLite store + audit log
│   └── pipeline.py           # end-to-end orchestration
├── api/main.py               # FastAPI REST API
├── ui/app.py                 # Streamlit app
├── scripts/                  # sample data generator, CLI, monthly job
├── config/coa_mapping.csv    # ledger → MIS category mapping (edit this for each client)
├── data/sample/              # synthetic GL + budget (with planted anomalies)
├── tests/test_copilot.py     # 13 tests
├── docs/DEPLOYMENT_AND_LOCALISATION.md
├── Dockerfile, docker-compose.yml, .env.example, .streamlit/config.toml
```

## Quick start (local laptop)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# 1) Optional: local LLM (https://ollama.com). Works without it, using rule-based commentary
ollama pull qwen2.5:7b-instruct

# 2) Generate the MIS pack from the sample data
python scripts/run_mis.py                 # add --no-llm to skip AI
#    -> output/MIS_2026-09.xlsx and output/MIS_2026-09.pdf

# 3) UI
streamlit run ui/app.py                   # http://localhost:8501

# 4) API
uvicorn api.main:app --port 8000          # http://localhost:8000/docs  (header X-API-Key)

# 5) Tests
python tests/test_copilot.py              # or: pytest -q
```

### API example
```bash
KEY=change-me-to-a-long-random-key
curl -X POST -H "X-API-Key: $KEY" "localhost:8000/analyze/sample?use_llm=false"
curl -H "X-API-Key: $KEY" localhost:8000/anomalies
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"question":"Which customers owe us the most?"}' localhost:8000/ask
curl -X POST -H "X-API-Key: $KEY" -F gl=@my_gl.xlsx -F budget=@budget.csv localhost:8000/upload
curl -H "X-API-Key: $KEY" -o mis.pdf localhost:8000/reports/pdf
```

## Using your own data

1. **Export the GL / Day Book** from Tally / Zoho / SAP as CSV/XLSX (or Tally Day Book XML). You need at least
   `date, voucher no, ledger/account, debit, credit` (or `amount` + `Dr/Cr`). A `party` column is used for ageing and duplicates.
2. **Edit `config/coa_mapping.csv`**: map every ledger to a category (`Revenue, COGS, Employee Cost, Admin Expenses,
   Marketing Expenses, Depreciation, Finance Cost, Other Income, Tax` for P&L; `Fixed Assets, Receivables, Inventory,
   Other Current Assets, Cash & Bank, Payables, Statutory Dues, Other Current Liabilities, Borrowings, Share Capital` for BS).
   The validator lists any unmapped ledgers.
3. **Budget** (optional): `month (YYYY-MM), category, amount`.
4. **Tally note:** party ledgers (customers/vendors) show up as accounts. Map each one (or bulk-map from the Tally group
   *Sundry Debtors / Sundry Creditors*) to `Receivables` / `Payables` so ageing works.
5. Opening balances: mark the opening voucher's narration with the word "Opening" so it isn't treated as a cash flow.

## Choosing a local LLM

| Hardware | Suggested model (Ollama tag) | Use |
|---|---|---|
| CPU / 16 GB RAM laptop | `qwen2.5:3b-instruct`, `llama3.2:3b` | Demo, slow |
| 1× 24 GB GPU (RTX 4090 / L4) | `qwen2.5:14b-instruct`, `llama3.1:8b` | Good commentary |
| 1–2× 80 GB GPU (A100/H100) via **vLLM** | Qwen2.5-32B/72B, Llama-3.3-70B | Best NL→SQL, multi-user |

For vLLM / TGI set `LLM_PROVIDER=openai_compatible` and `LLM_BASE_URL=http://<gpu-host>:8000/v1`.

## Data-localisation controls built in

- `localisation.assert_local_endpoint()` refuses any LLM/SMTP host that is not loopback, a private IP, a
  docker service name, or explicitly listed in `ALLOWED_LLM_HOSTS`. **Calls to OpenAI, Anthropic or Gemini public APIs are blocked.**
- `BLOCK_OUTBOUND_NETWORK=true` patches sockets process-wide, so library telemetry can't phone home.
- Party names are pseudonymised (`Party_001`), and PAN, GSTIN, Aadhaar, phone, email, IFSC and bank account numbers are masked before any prompt.
- `docker-compose.yml` puts the LLM on an `internal: true` network with no internet access.
- Streamlit telemetry is disabled. Every analysis, request, question and report is written to `logs/audit.log`.
- Use **synthetic data** (`scripts/generate_sample_data.py`) in development.

See **docs/DEPLOYMENT_AND_LOCALISATION.md** for hosting options (on-prem, India cloud regions, Indian sovereign clouds) and the go-live checklist.

## Roadmap (v1 → v2)
- PostgreSQL + pgvector, multi-tenant (company_id), Keycloak SSO/MFA, role-based access
- Connectors: Tally Prime ODBC/XML server, Zoho Books API, SAP OData, bank statement PDF parsing (pdfplumber + local OCR)
- Consolidation, inter-company eliminations, segment and cost-centre MIS
- GST reconciliation (GSTR-2B vs books), TDS checks
- React front-end, PowerPoint board pack (python-pptx), WhatsApp/Teams alerts
- Better forecasting (statsmodels/Prophet), IsolationForest anomalies, scenario planning
