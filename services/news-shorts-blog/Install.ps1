[CmdletBinding()]
param(
    [string]$BlogId = '',
    [string]$Category = '',
    [string]$Topic = '',
    [ValidateSet('chrome', 'chromium')]
    [string]$BrowserChannel = 'chrome'
)

$ErrorActionPreference = 'Stop'
if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is unavailable. Run this installer in your Windows user session.' }
$StateRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'GrowthvillainNewsAgent'))
$VenvRoot = Join-Path $StateRoot '.venv'
$AgentPython = Join-Path $VenvRoot 'Scripts\python.exe'
$ConfigPath = Join-Path $StateRoot 'config.json'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE. See the output above." }
}

function Assert-PythonVersion {
    param([string]$Executable, [string[]]$Prefix = @())
    # Windows PowerShell 5.1 strips embedded double quotes in native arguments.
    # Keep this Python snippet quote-free so it also works in that host.
    & $Executable @Prefix -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 3.11 or newer is required. Check the selected Python installation, then run Setup.cmd again.'
    }
}

New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath $AgentPython)) {
        $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($Launcher) {
            $PythonExecutable = $Launcher.Source
            $PythonPrefix = @('-3')
        } else {
            $Launcher = Get-Command python.exe -ErrorAction SilentlyContinue
            if (-not $Launcher) { throw 'Install Python 3.11 or newer from python.org, then run this installer again.' }
            $PythonExecutable = $Launcher.Source
            $PythonPrefix = @()
        }
        Assert-PythonVersion -Executable $PythonExecutable -Prefix $PythonPrefix
        Invoke-Checked -Executable $PythonExecutable -Arguments ($PythonPrefix + @('-m', 'venv', $VenvRoot))
    }
    Assert-PythonVersion -Executable $AgentPython
    Invoke-Checked -Executable $AgentPython -Arguments @('-m', 'pip', 'install', '-r', (Join-Path $PSScriptRoot 'requirements.txt'))

    $InitArguments = @('-m', 'news_agent', '--config', $ConfigPath, 'init')
    if ($BlogId) { $InitArguments += @('--blog-id', $BlogId) }
    if ($Category) { $InitArguments += @('--category', $Category) }
    Invoke-Checked -Executable $AgentPython -Arguments $InitArguments

    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "Setup did not create the configuration file: $ConfigPath. Run Setup.cmd again and check the configuration creation output."
    }
    try {
        $Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "Cannot read valid JSON from the configuration file: $ConfigPath. Run Diagnose.cmd to check the configuration."
    }
    $ConfigChanged = $false
    if ($PSBoundParameters.ContainsKey('BlogId')) {
        if ($BlogId -notmatch '^[A-Za-z0-9_-]{2,60}$') {
            throw 'BlogId must be the 2-60 character ID in your Naver blog URL, not the full URL.'
        }
        $Config | Add-Member -NotePropertyName blog_id -NotePropertyValue $BlogId -Force
        $ConfigChanged = $true
    } elseif (-not $Config.blog_id) {
        $EnteredBlogId = Read-Host 'Naver blog ID (from blog URL)'
        if ($EnteredBlogId -notmatch '^[A-Za-z0-9_-]{2,60}$') {
            throw 'Enter the 2-60 character blog ID only, then run Setup.cmd again.'
        }
        $Config | Add-Member -NotePropertyName blog_id -NotePropertyValue $EnteredBlogId -Force
        $ConfigChanged = $true
    }
    if ($PSBoundParameters.ContainsKey('Category')) {
        $CategoryValue = if ($Category) { $Category } else { $null }
        $Config | Add-Member -NotePropertyName category -NotePropertyValue $CategoryValue -Force
        $ConfigChanged = $true
    }
    if ($PSBoundParameters.ContainsKey('Topic')) {
        $TopicValue = if ($Topic) { $Topic } else { $null }
        $Config | Add-Member -NotePropertyName topic -NotePropertyValue $TopicValue -Force
        $ConfigChanged = $true
    }
    if ($PSBoundParameters.ContainsKey('BrowserChannel')) {
        $Config | Add-Member -NotePropertyName browser_channel -NotePropertyValue $BrowserChannel -Force
        $ConfigChanged = $true
    }
    if ($ConfigChanged) {
        $ConfigJson = $Config | ConvertTo-Json -Depth 20
        [System.IO.File]::WriteAllText($ConfigPath, $ConfigJson, (New-Object System.Text.UTF8Encoding($false)))
    }
    if ($Config.browser_channel -eq 'chromium') {
        Invoke-Checked -Executable $AgentPython -Arguments @('-m', 'playwright', 'install', 'chromium')
    } elseif ($Config.browser_channel -eq 'chrome') {
        $ChromePaths = @(
            (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'),
            (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe')
        )
        if (${env:ProgramFiles(x86)}) {
            $ChromePaths += Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'
        }
        $ChromePresent = @($ChromePaths | Where-Object { Test-Path -LiteralPath $_ }).Count -gt 0
        if (-not $ChromePresent) {
            throw 'Chrome was not found. Install Google Chrome, or rerun Install.ps1 -BrowserChannel chromium.'
        }
    } else {
        throw 'Unsupported browser_channel in config.json. Choose chrome or chromium.'
    }
    Invoke-Checked -Executable $AgentPython -Arguments @('-m', 'pip', 'check')
    Write-Host "Installed. Configuration: $ConfigPath"
    if (-not $Config.blog_id) { Write-Host 'Set blog_id in config.json before login or startup.' }
    Write-Host 'Next: run Login.cmd to complete login, then Start.cmd to start monitoring and publication.'
    Write-Host 'Installation does not start monitoring or publish a blog post.'
} finally {
    Pop-Location
}
