param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$FrontendBuild = Join-Path $Root "frontend\dist\index.html"

if (-not (Test-Path $Python)) {
    throw "Python environment not found. Run .\setup-windows.ps1 first."
}

if (-not (Test-Path $FrontendBuild)) {
    throw "Frontend build not found. Run .\setup-windows.ps1 first."
}

Write-Host "Starting Svelte + Python on port $Port..." -ForegroundColor Green
Write-Host "Open http://localhost:$Port in a browser."

Push-Location $Backend
try {
    & $Python -m uvicorn app.main:app --host 0.0.0.0 --port $Port
}
finally {
    Pop-Location
}

