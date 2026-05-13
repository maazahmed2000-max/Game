# One-shot: create public GitHub repo from this folder and push (GitHub Pages workflow runs on push).
# Prereq: run `gh auth login` once from the same machine.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$ghCandidates = @(
    "$env:ProgramFiles\GitHub CLI\gh.exe",
    "${env:ProgramFiles(x86)}\GitHub CLI\gh.exe"
)
$gh = $ghCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gh) { $gh = "gh" }

$p = Start-Process -FilePath $gh -ArgumentList @("auth", "status") -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput "$env:TEMP\gh-out.txt" -RedirectStandardError "$env:TEMP\gh-err.txt"
if ($p.ExitCode -ne 0) {
    Write-Host "Not logged in. Run this first, then re-run this script:" -ForegroundColor Yellow
    Write-Host "  gh auth login" -ForegroundColor Cyan
    exit 1
}

if (-not (Test-Path "$repoRoot\.git")) {
    Write-Error "No .git folder. Run from repo after git init + first commit."
}

$remotes = @(git remote 2>$null)
if ($remotes -contains "origin") {
    Write-Host "Remote 'origin' already exists. Pushing..."
    git push -u origin HEAD
    exit $LASTEXITCODE
}

# Change if this name is taken on your account
$REPO_NAME = "coop-kitchen-wasm"

Write-Host "Creating GitHub repo '$REPO_NAME' and pushing..."
$p2 = Start-Process -FilePath $gh -ArgumentList @(
    "repo", "create", $REPO_NAME,
    "--public", "--source=.", "--remote=origin", "--push",
    "--description", "Co-op kitchen game (pygame + pygbag / GitHub Pages)"
) -Wait -PassThru -NoNewWindow -WorkingDirectory $repoRoot

if ($p2.ExitCode -ne 0) {
    Write-Host ""
    Write-Host "If the name was taken, edit REPO_NAME in scripts\push_to_github.ps1 and run again." -ForegroundColor Yellow
    exit $p2.ExitCode
}

Write-Host ""
Write-Host "Done. Next: GitHub repo → Settings → Pages → Source: GitHub Actions." -ForegroundColor Green
Write-Host "After the workflow runs, your game URL is in the workflow summary." -ForegroundColor Green
