@echo off
cd /d "%~dp0"
set LOG=logs\step1_check.log
echo ===== STEP 1 CHECK %date% %time% ===== > %LOG%
echo --- python --version >> %LOG%
python --version >> %LOG% 2>&1
echo --- where python >> %LOG%
where python >> %LOG% 2>&1
echo --- py -0p (all installed Pythons) >> %LOG%
py -0p >> %LOG% 2>&1
echo --- pip --version >> %LOG%
python -m pip --version >> %LOG% 2>&1
echo --- where ollama >> %LOG%
where ollama >> %LOG% 2>&1
echo --- ollama --version >> %LOG%
ollama --version >> %LOG% 2>&1
echo --- ollama list >> %LOG%
ollama list >> %LOG% 2>&1
echo --- ollama API tags >> %LOG%
curl -s http://localhost:11434/api/tags >> %LOG% 2>&1
echo. >> %LOG%
echo ===== DONE ===== >> %LOG%
