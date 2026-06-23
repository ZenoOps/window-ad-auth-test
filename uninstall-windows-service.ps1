#Requires -RunAsAdministrator

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServiceId = "SvelteLitestarApp"
$Wrapper = Join-Path $Root "service\SvelteLitestarService.exe"
$ExistingService = Get-Service -Name $ServiceId -ErrorAction SilentlyContinue

if (-not $ExistingService) {
    Write-Host "$ServiceId is not installed." -ForegroundColor Yellow
    exit 0
}

if (-not (Test-Path $Wrapper)) {
    throw "WinSW executable not found at $Wrapper."
}

if ($ExistingService.Status -ne "Stopped") {
    & $Wrapper stop
    if ($LASTEXITCODE -ne 0) {
        throw "WinSW could not stop the service."
    }
}

& $Wrapper uninstall
if ($LASTEXITCODE -ne 0) {
    throw "WinSW could not uninstall the service."
}

Write-Host "$ServiceId was removed. Application files and logs were preserved." -ForegroundColor Green
