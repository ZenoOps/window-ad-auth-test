$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "WinGet is required to install Node.js and Python automatically."
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Node.js LTS..." -ForegroundColor Cyan

    winget install `
        --id OpenJS.NodeJS.LTS `
        -e `
        --accept-package-agreements `
        --accept-source-agreements

    Write-Host "Node.js was installed. Restart PowerShell and run this script again." `
        -ForegroundColor Yellow
    exit
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is unavailable. Restart PowerShell after installing Node.js."
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Python 3.13..." -ForegroundColor Cyan

    winget install `
        --id Python.Python.3.13 `
        -e `
        --accept-package-agreements `
        --accept-source-agreements

    Write-Host "Python was installed. Restart PowerShell and run this script again." `
        -ForegroundColor Yellow
    exit
}

