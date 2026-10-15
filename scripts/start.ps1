# Start the agatesim web app on Windows: installs and builds what's missing, then serves.
#
#   .\scripts\start.ps1            # opens http://127.0.0.1:8000/ in your browser
#   .\scripts\start.ps1 -Rebuild   # rebuild the web UI first (after pulling changes)

param([switch]$Rebuild, [int]$Port = 8000)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Pick up tools installed since this shell started.
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [Environment]::GetEnvironmentVariable("Path", "User")

uv sync --quiet

$built = Test-Path "src\agatesim\server\static\index.html"
if ($Rebuild -or -not $built) {
    Write-Host "Building the web UI..."
    npm --prefix web ci --silent
    npm --prefix web run build --silent
}

uv run agatesim serve --port $Port
