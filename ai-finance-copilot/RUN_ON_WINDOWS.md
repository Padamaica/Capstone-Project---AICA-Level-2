# AI Finance Co-Pilot – Run Guide (Windows, Python 3.15 + Ollama)

Verified on this laptop on 31-Oct-2026: Python 3.15.1, Ollama 0.40.13, model qwen2.5:3b-instruct, **16/16 tests passed**.

## Month-end routine (3 steps, about 3 minutes)
1. Open `templates\MIS_Input_Template.xlsx`. Paste the GL / Day Book into the **GL** sheet, the budget into **Budget**, and add any new ledger to **Mapping**.
2. Save it as `input\MIS_Input_<Mon-YYYY>.xlsx`.
3. Double-click **`RUN_MIS.bat`**. The output folder `output\<YYYY-MM>\` opens with the Excel MIS, PDF board pack, AI commentary and run summary.

If a ledger is not mapped or a voucher does not balance, the run stops and opens `output\VALIDATION_ERRORS.txt` showing exactly what to fix. No wrong report is ever produced.

For a live demo, double-click **`START_DASHBOARD.bat`**, choose **Excel template (1 file)**, upload the workbook and click **Run analysis**.

## Folder map
| Folder / file | Purpose |
|---|---|
| `templates\MIS_Input_Template.xlsx` | Blank monthly input (README, GL, Budget, Mapping with dropdowns) |
| `input\` | Put the filled workbook here (`MIS_Input_Sample_Sep-2026.xlsx` = demo data) |
| `output\<YYYY-MM>\` | Reports for each month |
| `RUN_MIS.bat` / `START_DASHBOARD.bat` | Month-end batch run / interactive dashboard |
| `run_windows.bat` | Full self-check (tests + sample run + dashboard) |

## One click (full self-check)
Double-click **`run_windows.bat`**. It runs the tests, builds the MIS pack with AI commentary, opens the PDF and starts the dashboard at http://localhost:8501.

## Manual commands (Command Prompt)
```bat
cd "C:\Users\Padam Jain\Downloads\Capstone Project\ai-finance-copilot"
"%LOCALAPPDATA%\Programs\Ollama\ollama.exe" list              :: model must show qwen2.5:3b-instruct
.venv\Scripts\python.exe scripts\generate_sample_data.py      :: fresh synthetic GL + budget
.venv\Scripts\python.exe tests\test_copilot.py                :: expect 16/16 passed
.venv\Scripts\python.exe scripts\run_from_excel.py            :: newest workbook in input\ -> output\<month>\
.venv\Scripts\python.exe scripts\final_run.py                 :: MIS pack + AI commentary + Q&A (sample CSV)
.venv\Scripts\python.exe -m streamlit run ui\app.py           :: dashboard
.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000  :: REST API (http://localhost:8000/docs)
```

## Important on this laptop
| Point | Detail |
|---|---|
| Do not use `python` | It opens the Microsoft Store alias. Use `py -3.15` or `.venv\Scripts\python.exe` |
| `pip install ollama` is not Ollama | It is only the Python client. The server app is installed at `%LOCALAPPDATA%\Programs\Ollama` |
| Python 3.15 requirements | Use `requirements-py315.txt`. `uvicorn[standard]` fails because pyyaml has no 3.15 wheel yet; plain `uvicorn` works |
| Ollama must be running | Tray icon, or `ollama.exe serve`. If it is off, the tool falls back to rule-based commentary |

## Outputs (folder `output`)
- `MIS_2026-09.xlsx`: 11 sheets (Summary, P&L, BS, Cash Flow, Ratios, BvA, AR/AP ageing, Anomalies, Forecast, Data Quality)
- `MIS_2026-09.pdf`: board pack with charts and commentary
- `AI_Output_2026-09.md`: AI commentary and "Ask your data" Q&A, including the SQL used

## AI controls (why the numbers can be trusted)
1. Python calculates every number. The LLM only writes the words.
2. Commentary numeric guard: if the LLM invents numbers, it retries once, then falls back to rule-based commentary.
3. Q&A: known question types run pre-tested SQL. Amounts are pre-formatted in L/Cr. Any number the LLM changes is caught, and Python's own summary is used instead.
4. PII masking: customer and vendor names become Party_001 etc. before the LLM sees them. Everything runs locally (data localisation).
