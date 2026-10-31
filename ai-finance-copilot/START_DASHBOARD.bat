@echo off
REM AI Finance Co-Pilot - interactive dashboard for the meeting (http://localhost:8501)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
title AI Finance Co-Pilot - Dashboard
curl -s http://localhost:11434/api/tags >nul 2>&1 || start "Ollama server" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
.venv\Scripts\python.exe -m streamlit run ui\app.py --server.headless false
pause
