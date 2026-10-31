@echo off
cd /d "%~dp0"
set LOG=logs\step3_install.log
echo ===== STEP 3 INSTALL %date% %time% ===== > %LOG%
.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-py315.txt >> %LOG% 2>&1
echo PIP_EXIT=%errorlevel% >> %LOG%
.venv\Scripts\python.exe -m pip list >> %LOG% 2>&1
echo ===== DONE ===== >> %LOG%
