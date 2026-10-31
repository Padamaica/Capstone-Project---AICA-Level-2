@echo off
cd /d "%~dp0"
set LOG=logs\probe.log
echo ===== PROBE %date% %time% ===== > %LOG%
tasklist | findstr /i "ollama winget AppInstaller" >> %LOG% 2>&1
dir /s /-c "%TEMP%\WinGet" 2>nul | findstr /i "OllamaSetup" >> %LOG%
dir "%LOCALAPPDATA%\Programs\Ollama" >> %LOG% 2>&1
curl -s http://localhost:11434/api/tags >> %LOG% 2>&1
echo. >> %LOG%
type logs\step4_pull_progress.log >> %LOG% 2>nul
