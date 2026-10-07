param([int]$Port = 4177)
$ErrorActionPreference = 'Stop'
$runtimePython = Join-Path $env:LOCALAPPDATA 'JoWooHyung/MetaAds/runtime/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
    $pythonCommand = Get-Command pythonw -ErrorAction SilentlyContinue
    if ($pythonCommand) { $runtimePython = $pythonCommand.Source }
    else { throw 'Python runtime not found. Run Launch-MetaAds.ps1 -Setup first.' }
}
# This visible window is explicitly requested by the user. No console is opened.
$scriptPath = Join-Path $PSScriptRoot 'desktop_status.py'
Start-Process -FilePath $runtimePython -ArgumentList @(('"' + $scriptPath + '"'), '--port', "$Port") -WorkingDirectory $PSScriptRoot
