@echo off
cd /d "%~dp0"
set LOG=logs\step2_setup.log
echo ===== STEP 2 SETUP %date% %time% ===== > %LOG%
echo --- Looking for Ollama >> %LOG%
dir /b "%LOCALAPPDATA%\Programs\Ollama" >> %LOG% 2>&1
dir /b "%ProgramFiles%\Ollama" >> %LOG% 2>&1
py -3.15 -m pip show ollama >> %LOG% 2>&1
tasklist | findstr /i ollama >> %LOG% 2>&1
echo --- Creating venv with Python 3.15 >> %LOG%
if not exist .venv py -3.15 -m venv .venv >> %LOG% 2>&1
.venv\Scripts\python.exe --version >> %LOG% 2>&1
.venv\Scripts\python.exe -m pip install --upgrade pip >> %LOG% 2>&1
echo --- Installing requirements >> %LOG%
.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt >> %LOG% 2>&1
echo PIP_EXIT=%errorlevel% >> %LOG%
.venv\Scripts\python.exe -m pip list >> %LOG% 2>&1
echo ===== DONE ===== >> %LOG%
