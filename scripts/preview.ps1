param([int]$Port = 4174)
$ErrorActionPreference = 'Stop'
$v2Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$v2LogRoot = Join-Path (Split-Path $v2Root -Parent) '.workspace-local'
New-Item -ItemType Directory -Path $v2LogRoot -Force | Out-Null
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
  $v2Existing = Get-CimInstance Win32_Process -Filter "ProcessId = $($_.OwningProcess)"
  if ($v2Existing.CommandLine -like "*http.server*$Port*" -and $v2Existing.CommandLine.Contains($v2Root)) {
    Stop-Process -Id $v2Existing.ProcessId
  }
}
Push-Location -LiteralPath $v2Root
try {
  py build_v2.py
  if ($LASTEXITCODE -ne 0) { throw 'Content build failed.' }
  py build_cloudflare.py
  if ($LASTEXITCODE -ne 0) { throw 'Static build failed.' }
  $v2Dist = (Resolve-Path -LiteralPath (Join-Path $v2Root 'dist')).Path
  $v2Arguments = @('-m','http.server',"$Port",'--bind','127.0.0.1','--directory',('"' + $v2Dist + '"'))
  $v2Server = Start-Process -FilePath 'py.exe' -ArgumentList $v2Arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $v2LogRoot 'portfolio-v2-server.log') -RedirectStandardError (Join-Path $v2LogRoot 'portfolio-v2-server-error.log')
  Write-Output "Preview: http://127.0.0.1:$Port/ (process $($v2Server.Id))"
} finally { Pop-Location }
