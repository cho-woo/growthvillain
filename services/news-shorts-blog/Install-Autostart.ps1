[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$TaskName = 'GrowthvillainNewsShortsAgent'
$AgentPython = Join-Path $env:LOCALAPPDATA 'GrowthvillainNewsAgent\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $AgentPython)) { throw 'Run Install.ps1 first.' }
$StartFile = Join-Path $PSScriptRoot 'Start.cmd'
if (-not (Test-Path -LiteralPath $StartFile)) { throw 'Start.cmd is missing.' }
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action = New-ScheduledTaskAction -Execute $env:ComSpec -Argument ('/d /s /c ""{0}""' -f $StartFile) -WorkingDirectory $PSScriptRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description 'Monitor same-day news Shorts and publish up to three source-linked Naver posts per KST day.' -Force | Out-Null
Write-Host "Registered $TaskName for your next Windows login. No password or administrator elevation is needed."
Write-Host 'Run Start.cmd now if you want to start this session. Complete authentication in the visible browser when requested.'
Write-Host ('Remove later: Unregister-ScheduledTask -TaskName ''{0}'' -Confirm:$false' -f $TaskName)
