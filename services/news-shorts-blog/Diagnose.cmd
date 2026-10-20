@echo off
setlocal
set "NEWS_AGENT_PYTHON=%LOCALAPPDATA%\GrowthvillainNewsAgent\.venv\Scripts\python.exe"
if not exist "%NEWS_AGENT_PYTHON%" (
  echo [VENV_MISSING] Run Setup.cmd first and check that installation finishes.
  pause
  exit /b 2
)
cd /d "%~dp0"
"%NEWS_AGENT_PYTHON%" -m news_agent diagnose
set "NEWS_AGENT_EXIT=%ERRORLEVEL%"
pause
exit /b %NEWS_AGENT_EXIT%
