@echo off
setlocal
set "NEWS_AGENT_PYTHON=%LOCALAPPDATA%\GrowthvillainNewsAgent\.venv\Scripts\python.exe"
if not exist "%NEWS_AGENT_PYTHON%" (
  echo Run Install.ps1 first.
  pause
  exit /b 1
)
cd /d "%~dp0"
"%NEWS_AGENT_PYTHON%" -m news_agent login
set "NEWS_AGENT_EXIT=%ERRORLEVEL%"
if not "%NEWS_AGENT_EXIT%"=="0" pause
exit /b %NEWS_AGENT_EXIT%
