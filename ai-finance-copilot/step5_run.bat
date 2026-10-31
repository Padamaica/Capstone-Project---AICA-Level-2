@echo off
cd /d "%~dp0"
set LOG=logs\step5_run.log
set PYTHONIOENCODING=utf-8
echo ===== STEP 5 RUN %date% %time% ===== > %LOG%
if not exist .env copy .env.example .env >nul
powershell -NoProfile -Command "$c = Get-Content .env; $c = $c -replace '^LLM_PROVIDER=.*','LLM_PROVIDER=ollama' -replace '^LLM_MODEL=.*','LLM_MODEL=qwen2.5:3b-instruct' -replace '^LLM_TIMEOUT_S=.*','LLM_TIMEOUT_S=900'; Set-Content .env $c -Encoding UTF8"
findstr /b "LLM_" .env >> %LOG%
curl -s http://localhost:11434/api/tags >nul 2>&1 || start "Ollama server" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
echo --- 1. Generate fresh sample data >> %LOG%
.venv\Scripts\python.exe scripts\generate_sample_data.py >> %LOG% 2>&1
echo --- 2. Tests >> %LOG%
.venv\Scripts\python.exe tests\test_copilot.py >> %LOG% 2>&1
echo --- 3. Full AI run >> %LOG%
.venv\Scripts\python.exe scripts\final_run.py >> %LOG% 2>&1
echo RUN_EXIT=%errorlevel% >> %LOG%
echo ===== DONE ===== >> %LOG%
