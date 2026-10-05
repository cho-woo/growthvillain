param(
    [int]$Port = 4177,
    [string]$WebRoot = '',
    [string]$DataDir = '',
    [switch]$Setup,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$serviceRoot = $PSScriptRoot
if (-not $WebRoot) { $WebRoot = [System.IO.Path]::GetFullPath((Join-Path $serviceRoot '../..')) }
$runtimeHome = Join-Path $env:LOCALAPPDATA 'JoWooHyung/MetaAds'
$venvRoot = Join-Path $runtimeHome 'runtime'
$runtimePython = Join-Path $venvRoot 'Scripts/python.exe'
function Find-PersonalPython {
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($name in @('python', 'python3', 'py')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source -and $command.Source -notmatch '\\WindowsApps\\') {
            $candidates.Add($command.Source)
        }
    }
    if ($env:USERPROFILE) {
        $candidates.Add((Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'))
    }
    if ($env:LOCALAPPDATA) {
        foreach ($version in @('314', '313', '312', '311')) {
            $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs/Python/Python$version/python.exe"))
        }
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $probe = & $candidate -c 'import sys; print("ready" if sys.version_info >= (3, 11) else "old")' 2>$null
        if ($LASTEXITCODE -eq 0 -and $probe -eq 'ready') { return $candidate }
    }
    throw 'Python 3.11 or newer was not found. Install Python or open this project from Codex and retry.'
}
if (-not (Test-Path -LiteralPath $runtimePython)) {
    if (-not $Setup) {
        Write-Host 'First run: use Launch-MetaAds.ps1 -Setup to install the personal local runtime.'
        exit 1
    }
    $basePython = Find-PersonalPython
    New-Item -ItemType Directory -Force -Path $runtimeHome | Out-Null
    & $basePython -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
}
if ($Setup) {
    & $runtimePython -m pip install -r (Join-Path $serviceRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
    & $runtimePython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
}
$resolveArguments = @((Join-Path $serviceRoot 'storage_config.py'), '--json')
if ($DataDir) { $resolveArguments += @('--data-dir', $DataDir) }
$resolvedStorage = & $runtimePython @resolveArguments
if ($LASTEXITCODE -ne 0) { throw 'The configured storage folder is unavailable. Connect the selected drive and retry. No fallback folder was used.' }
$DataDir = ($resolvedStorage | ConvertFrom-Json).dataDir
Write-Host ('Ad storage: ' + $DataDir)
$serverArguments = @((Join-Path $serviceRoot 'server.py'), '--web-root', $WebRoot, '--data-dir', $DataDir, '--port', $Port)
if (-not $NoBrowser) { $serverArguments += '--open' }
& $runtimePython @serverArguments
