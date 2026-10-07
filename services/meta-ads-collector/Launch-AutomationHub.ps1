$ErrorActionPreference = 'Stop'
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\pythonw.exe'
$launcher = Join-Path $PSScriptRoot 'launch_hub.py'
Start-Process -FilePath $python -ArgumentList "`"$launcher`" --widget" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
