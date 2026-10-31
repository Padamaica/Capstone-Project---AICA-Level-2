@echo off
REM AI Finance Co-Pilot - one click (Python 3.15 + local Ollama). Double-click to run.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist .venv (
  echo Creating virtual environment with Python 3.15 ...
  py -3.15 -m venv .venv
  .venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-py315.txt
)
if not exist .env (
  copy .env.example .env >nul
  powershell -NoProfile -Command "$c = Get-Content .env; $c = $c -replace '^LLM_MODEL=.*','LLM_MODEL=qwen2.5:3b-instruct' -replace '^LLM_TIMEOUT_S=.*','LLM_TIMEOUT_S=900'; Set-Content .env $c -Encoding UTF8"
)
curl -s http://localhost:11434/api/tags >nul 2>&1 || start "Ollama server" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
echo.
echo === 1/3 Tests ===
.venv\Scripts\python.exe tests\test_copilot.py
echo.
echo === 2/3 MIS pack + AI commentary + Ask-your-data (3-4 min on CPU) ===
.venv\Scripts\python.exe scripts\final_run.py
start "" output\MIS_2026-09.pdf
echo.
echo === 3/3 Dashboard: http://localhost:8501  (close this window to stop) ===
.venv\Scripts\python.exe -m streamlit run ui\app.py
pause
