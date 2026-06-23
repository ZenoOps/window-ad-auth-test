#Requires -RunAsAdministrator

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$FrontendBuild = Join-Path $Root "frontend\dist\index.html"
$ServiceDirectory = Join-Path $Root "service"
$ServiceId = "SvelteLitestarApp"
$Wrapper = Join-Path $ServiceDirectory "SvelteLitestarService.exe"
$Configuration = Join-Path $ServiceDirectory "SvelteLitestarService.xml"
$WinSwUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"

if (-not (Test-Path $Python)) {
    throw "Python environment not found. Run .\setup-windows.ps1 first."
}

if (-not (Test-Path $FrontendBuild)) {
    throw "Compiled frontend not found. Run .\setup-windows.ps1 first."
}

if (-not (Test-Path $Configuration)) {
    throw "WinSW configuration not found at $Configuration."
}

New-Item -ItemType Directory -Force -Path (Join-Path $ServiceDirectory "logs") | Out-Null

if (-not (Test-Path $Wrapper)) {
    Write-Host "Downloading WinSW 2.12.0..." -ForegroundColor Cyan
    Invoke-WebRequest -UseBasicParsing -Uri $WinSwUrl -OutFile $Wrapper
}

$ExistingService = Get-Service -Name $ServiceId -ErrorAction SilentlyContinue
if ($ExistingService) {
    Write-Host "Replacing the existing $ServiceId service..." -ForegroundColor Yellow

    if ($ExistingService.Status -ne "Stopped") {
        & $Wrapper stop
        if ($LASTEXITCODE -ne 0) {
            throw "WinSW could not stop the existing service."
        }
    }

    & $Wrapper uninstall
    if ($LASTEXITCODE -ne 0) {
        throw "WinSW could not uninstall the existing service."
    }
}

Write-Host "Installing $ServiceId..." -ForegroundColor Cyan
& $Wrapper install
if ($LASTEXITCODE -ne 0) {
    throw "WinSW could not install the service."
}

& $Wrapper start
if ($LASTEXITCODE -ne 0) {
    throw "WinSW could not start the service. Check service\logs for details."
}

$InstalledService = Get-Service -Name $ServiceId
$InstalledService.WaitForStatus(
    [System.ServiceProcess.ServiceControllerStatus]::Running,
    [TimeSpan]::FromSeconds(30)
)
$InstalledService.Refresh()

Write-Host "$ServiceId is $($InstalledService.Status)." -ForegroundColor Green
Write-Host "Open http://localhost:9090"
Write-Host "Logs: $ServiceDirectory\logs"
