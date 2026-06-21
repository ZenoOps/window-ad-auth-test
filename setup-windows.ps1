$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is not installed or is not available in PATH."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is not installed or is not available in PATH."
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python's 'py' launcher is not installed or is not available in PATH."
}

Write-Host "Installing and building the Svelte frontend..." -ForegroundColor Cyan
Push-Location $Frontend
try {
    npm install
    npm run build
}
finally {
    Pop-Location
}

Write-Host "Creating the Python environment..." -ForegroundColor Cyan
if (-not (Test-Path $Python)) {
    & py -3 -m venv (Join-Path $Backend ".venv")
}

& $Python -m pip install -r (Join-Path $Backend "requirements.txt")

Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Start the application with: .\run-windows.ps1"

