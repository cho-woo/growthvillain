$ErrorActionPreference = 'Stop'
$localPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\pythonw.exe'
$launcher = Join-Path $PSScriptRoot 'launch_hub.py'
if (-not (Test-Path -LiteralPath $localPython)) { throw 'Python 3.12 runtime not found.' }
$action = New-ScheduledTaskAction -Execute $localPython -Argument "`"$launcher`"" -WorkingDirectory $PSScriptRoot
$loginAction = New-ScheduledTaskAction -Execute $localPython -Argument "`"$launcher`" --widget" -WorkingDirectory $PSScriptRoot
$owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $owner -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -MultipleInstances IgnoreNew
$loginTrigger = New-ScheduledTaskTrigger -AtLogOn -User $owner
$checkTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'GrowthvillainAutomationHub' -Action $loginAction -Trigger $loginTrigger -Principal $principal -Settings $settings -Description 'Local automation server and desktop status at sign-in. Persisted ON/OFF controls are respected.' -Force | Out-Null
Register-ScheduledTask -TaskName 'GrowthvillainAutomationHubHealth' -Action $action -Trigger $checkTrigger -Principal $principal -Settings $settings -Description 'Restart the local automation server if it stops. No new publication is forced.' -Force | Out-Null
Write-Output 'Automation hub logon and five-minute recovery tasks registered.'
