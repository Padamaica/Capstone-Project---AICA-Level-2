@echo off
cd /d "%~dp0"
set LOG=logs\step4_ollama.log
set OLL=%LOCALAPPDATA%\Programs\Ollama\ollama.exe
echo ===== STEP 4 OLLAMA %date% %time% ===== > %LOG%
if not exist "%OLL%" (
  echo --- Installing Ollama via winget >> %LOG%
  winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements >> %LOG% 2>&1
  echo WINGET_EXIT=%errorlevel% >> %LOG%
)
if not exist "%OLL%" (
  echo OLLAMA_NOT_FOUND_AFTER_INSTALL >> %LOG%
  goto end
)
"%OLL%" --version >> %LOG% 2>&1
echo --- Starting Ollama server >> %LOG%
curl -s http://localhost:11434/api/tags >nul 2>&1 || start "Ollama server" /min "%OLL%" serve
timeout /t 8 /nobreak >nul
echo --- Pulling qwen2.5:3b-instruct >> %LOG%
"%OLL%" pull qwen2.5:3b-instruct > logs\step4_pull_progress.log 2>&1
echo PULL_EXIT=%errorlevel% >> %LOG%
"%OLL%" list >> %LOG% 2>&1
:end
echo ===== DONE ===== >> %LOG%
