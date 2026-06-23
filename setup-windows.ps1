$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$BackendEnv = Join-Path $Backend ".env"
$BackendEnvExample = Join-Path $Backend ".env.example"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Node.js is missing and WinGet is unavailable. Install Node.js LTS manually."
    }

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
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python is missing and WinGet is unavailable. Install Python 3 manually."
    }

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

if (-not (Test-Path $BackendEnv)) {
    Copy-Item $BackendEnvExample $BackendEnv
    Write-Host "Created backend\.env. Configure the Casdoor application values before using authentication." `
        -ForegroundColor Yellow
}
else {
    $RequiredSettings = @(
        "CASDOOR_APPLICATION",
        "CASDOOR_CLIENT_ID",
        "CASDOOR_CLIENT_SECRET",
        "CASDOOR_REDIRECT_URI"
    )
    $EnvironmentText = Get-Content $BackendEnv -Raw
    $MissingSettings = @(
        $RequiredSettings | Where-Object {
            $EnvironmentText -notmatch "(?m)^$($_)\s*=\s*\S+"
        }
    )

    if ($MissingSettings.Count -gt 0) {
        Write-Host "backend\.env needs these authentication settings: $($MissingSettings -join ', ')" `
            -ForegroundColor Yellow
    }
}

Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Run manually with: .\run-windows.ps1 or use WindowSW to install as a service with: .\install-windows-service.ps1" -ForegroundColor Yellow
Write-Host "Install as a service with Administrator PowerShell: .\install-windows-service.ps1"
Write-Host "Create a fallback account with: & .\backend\.venv\Scripts\python.exe .\backend\create_local_user.py"
