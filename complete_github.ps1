# Run this from the Game folder after you install GitHub CLI.
# 1) Logs you into GitHub in the browser (if needed)
# 2) Creates the public repo and pushes (starts GitHub Pages build)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$gh = @(
    "$env:ProgramFiles\GitHub CLI\gh.exe",
    "${env:ProgramFiles(x86)}\GitHub CLI\gh.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gh) { $gh = "gh" }

$p = Start-Process -FilePath $gh -ArgumentList @("auth", "status") -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput "$env:TEMP\gh-out.txt" -RedirectStandardError "$env:TEMP\gh-err.txt"
if ($p.ExitCode -ne 0) {
    Write-Host "Logging in to GitHub (browser will open). Follow the prompts, then this script continues." -ForegroundColor Cyan
    & $gh auth login -h github.com -p https -w
}

& "$PSScriptRoot\scripts\push_to_github.ps1"
