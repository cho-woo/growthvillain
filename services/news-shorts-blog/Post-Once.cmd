@echo off
setlocal
set "NEWS_AGENT_PYTHON=%LOCALAPPDATA%\GrowthvillainNewsAgent\.venv\Scripts\python.exe"
if not exist "%NEWS_AGENT_PYTHON%" (
  echo Run Setup.cmd first.
  pause
  exit /b 1
)
cd /d "%~dp0"
"%NEWS_AGENT_PYTHON%" -m news_agent once
set "NEWS_AGENT_EXIT=%ERRORLEVEL%"
pause
exit /b %NEWS_AGENT_EXIT%
