# Build browser version (WebAssembly) into build\web
# Prereq: Python 3.11+ with pip
# Usage: .\build_web.ps1
# Must run from this folder so pygbag.ini is picked up.
#
# Test locally (same Wi-Fi for phone):
#   cd build\web
#   py -m http.server 8000
# On phone: http://YOUR_PC_LAN_IP:8000

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

py -m pip install --upgrade pygbag pygame-ce 2>$null
py -m pygbag --build --ume_block 0 .

Write-Host ""
Write-Host "Built: $PSScriptRoot\build\web"
Write-Host "Quick test: py -m http.server 8000 --directory `"$PSScriptRoot\build\web`""
Write-Host "Then open http://localhost:8000  (phone: use your PC LAN IP instead of localhost)"
