@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
set "NEWS_AGENT_EXIT=%ERRORLEVEL%"
pause
exit /b %NEWS_AGENT_EXIT%
