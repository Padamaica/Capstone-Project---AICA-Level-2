@echo off
REM ============================================================
REM  AI Finance Co-Pilot - MONTH-END RUN
REM  1. Save filled template as input\MIS_Input_<Mon-YYYY>.xlsx
REM  2. Double-click this file. Reports open automatically.
REM ============================================================
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
title AI Finance Co-Pilot - Month-end run
curl -s http://localhost:11434/api/tags >nul 2>&1 || start "Ollama server" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
timeout /t 3 /nobreak >nul
.venv\Scripts\python.exe scripts\run_from_excel.py %*
if errorlevel 1 (
  echo.
  echo  Run stopped. Opening VALIDATION_ERRORS.txt ...
  start "" notepad output\VALIDATION_ERRORS.txt
  pause
  exit /b 1
)
for /f "delims=" %%d in ('dir /b /ad /o-d output\20* 2^>nul') do (set LATEST=%%d& goto :open)
:open
start "" explorer "output\%LATEST%"
start "" "output\%LATEST%\MIS_%LATEST%.pdf"
echo.
echo  Done. Reports are in output\%LATEST%
pause
