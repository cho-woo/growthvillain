param(
    [string]$Repository = '',
    [string]$CommitMessage = 'Update public Meta ad archive',
    [switch]$Pause
)
# Public-only archive synchronization, manually or by the authorized local scheduler.
$ErrorActionPreference = 'Stop'
# Decode native Git output consistently when launched with CREATE_NO_WINDOW.
# A legacy console code page otherwise corrupts Korean repository paths.
$archiveUtf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $archiveUtf8
$OutputEncoding = $archiveUtf8
try {
    if (-not $Repository) { $Repository = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..')) }
    $Repository = (Resolve-Path -LiteralPath $Repository).Path
    $gitCandidates = [System.Collections.Generic.List[string]]::new()
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    if ($gitCommand -and $gitCommand.Source) { $gitCandidates.Add($gitCommand.Source) }
    if ($env:ProgramFiles) { $gitCandidates.Add((Join-Path $env:ProgramFiles 'Git/cmd/git.exe')) }
    if ($env:LOCALAPPDATA) { $gitCandidates.Add((Join-Path $env:LOCALAPPDATA 'Programs/Git/cmd/git.exe')) }
    if ($env:USERPROFILE) {
        $gitCandidates.Add((Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'))
    }
    $script:archiveGit = $gitCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $script:archiveGit) { throw 'Git was not found. Install Git for Windows or start from Codex.' }

    function Invoke-ArchiveGit {
        param([string[]]$Arguments, [string]$Failure = 'Git operation failed.')
        # Capture all output: credential-bearing remote URLs or authentication errors are never printed.
        $previousErrorPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $result = & $script:archiveGit -c core.quotepath=false -C $Repository @Arguments 2>&1
            $gitExitCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $previousErrorPreference }
        if ($gitExitCode -ne 0) { throw $Failure }
        return @($result | ForEach-Object { [string]$_ })
    }
    function Assert-ArchivePaths {
        param([string[]]$Paths)
        foreach ($path in $Paths) {
            if ($path -and $path -notmatch '^tools/meta-ads/(data|media)/[^\r\n]+$') {
                throw 'Unrelated staged or unpublished changes were found. Finish those changes separately before publishing the archive.'
            }
        }
    }

    $top = @(Invoke-ArchiveGit -Arguments @('rev-parse', '--show-toplevel'))
    if ($top.Count -ne 1 -or [System.IO.Path]::GetFullPath($top[0]) -ne [System.IO.Path]::GetFullPath($Repository)) {
        throw 'The selected folder is not the repository root.'
    }
    $expectedRemote = '^(https://github\.com/cho-woo/growthvillain(?:\.git)?/?|git@github\.com:cho-woo/growthvillain(?:\.git)?|ssh://git@github\.com/cho-woo/growthvillain(?:\.git)?)$'
    foreach ($remoteArgs in @(@('remote', 'get-url', '--all', 'origin'), @('remote', 'get-url', '--push', '--all', 'origin'))) {
        $urls = @(Invoke-ArchiveGit -Arguments $remoteArgs)
        if ($urls.Count -ne 1 -or $urls[0] -notmatch $expectedRemote) {
            throw 'Origin must point only to cho-woo/growthvillain on GitHub. Nothing was published.'
        }
    }
    $branch = @(Invoke-ArchiveGit -Arguments @('branch', '--show-current'))
    if ($branch.Count -ne 1 -or $branch[0] -ne 'master') { throw 'Switch to the master branch before publishing the archive.' }
    $staged = @(Invoke-ArchiveGit -Arguments @('diff', '--cached', '--name-only', '--diff-filter=ACDMRTUXB'))
    Assert-ArchivePaths -Paths $staged

    $catalogPath = Join-Path $Repository 'tools/meta-ads/data/catalog.json'
    if (-not (Test-Path -LiteralPath $catalogPath -PathType Leaf)) { throw 'The public catalog is missing. Collect or export ads first.' }
    $catalog = Get-Content -LiteralPath $catalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($catalog.version -ne 1 -or $null -eq $catalog.cards) { throw 'The public catalog format is invalid.' }
    Write-Host ('Publishing the reviewed public archive: {0} ads.' -f @($catalog.cards).Count)

    $null = Invoke-ArchiveGit -Arguments @('fetch', '--quiet', '--no-tags', 'origin', 'master') -Failure 'Could not check GitHub. Check your network and Git authentication, then retry.'
    $behind = @(Invoke-ArchiveGit -Arguments @('rev-list', '--count', 'HEAD..origin/master'))
    if ($behind[0] -ne '0') { throw 'GitHub contains newer changes. Update the project before publishing; no merge is attempted automatically.' }
    # A previous failed push may leave archive-only commits; retry them without including other work.
    $aheadPaths = @(Invoke-ArchiveGit -Arguments @('log', '--format=', '--name-only', 'origin/master..HEAD'))
    Assert-ArchivePaths -Paths $aheadPaths
    $null = Invoke-ArchiveGit -Arguments @('add', '--', 'tools/meta-ads/data', 'tools/meta-ads/media')
    $staged = @(Invoke-ArchiveGit -Arguments @('diff', '--cached', '--name-only'))
    Assert-ArchivePaths -Paths $staged
    if ($staged.Count -gt 0) {
        $null = Invoke-ArchiveGit -Arguments @('diff', '--cached', '--check') -Failure 'The staged archive failed validation.'
        $null = Invoke-ArchiveGit -Arguments @('commit', '-m', $CommitMessage) -Failure 'Could not create the archive commit. Check your Git name/email settings.'
    }
    $aheadPaths = @(Invoke-ArchiveGit -Arguments @('log', '--format=', '--name-only', 'origin/master..HEAD'))
    Assert-ArchivePaths -Paths $aheadPaths
    $ahead = @(Invoke-ArchiveGit -Arguments @('rev-list', '--count', 'origin/master..HEAD'))
    if ($ahead[0] -eq '0') {
        Write-Host 'The public archive is already up to date. No push was needed.'
    } else {
        $null = Invoke-ArchiveGit -Arguments @('push', 'origin', 'HEAD:refs/heads/master') -Failure 'GitHub push failed. Your archive commit is saved locally. Check Git authentication and retry this file.'
        Write-Host 'Public archive pushed to GitHub. Netlify will publish it when the connected build succeeds.'
    }
    Write-Host 'Website: https://1jang2.netlify.app/tools/meta-ads/'
} catch {
    Write-Host ('Publication stopped: ' + $_.Exception.Message) -ForegroundColor Red
    if ($Pause) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}
if ($Pause) { Read-Host 'Press Enter to close' | Out-Null }
