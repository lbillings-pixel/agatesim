# Start the agatesim web app on Windows: installs and builds what's missing, then serves.
#
#   .\scripts\start.ps1            # opens http://127.0.0.1:8000/ in your browser
#   .\scripts\start.ps1 -Rebuild   # rebuild the web UI first (after pulling changes)
#   .\scripts\start.ps1 -Gpu       # install the GPU extra (CuPy, NVIDIA only) and use it
#
# An installed GPU extra is kept: a plain `uv sync` or `uv run` would remove it.

param([switch]$Rebuild, [switch]$Gpu, [int]$Port = 8000)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Pick up tools installed since this shell started.
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [Environment]::GetEnvironmentVariable("Path", "User")

$hasGpu = $false
if (-not $Gpu) {
    # A failed import writes to stderr, which "Stop" would turn into an error.
    $ErrorActionPreference = "Continue"
    uv run --no-sync python -c "import cupy" *> $null
    $hasGpu = $LASTEXITCODE -eq 0
    $ErrorActionPreference = "Stop"
}
if ($Gpu -or $hasGpu) { uv sync --quiet --extra gpu } else { uv sync --quiet }

$built = Test-Path "src\agatesim\server\static\index.html"
if ($Rebuild -or -not $built) {
    Write-Host "Building the web UI..."
    npm --prefix web ci --silent
    npm --prefix web run build --silent
}

uv run --no-sync agatesim serve --port $Port
