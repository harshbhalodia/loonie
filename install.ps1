#requires -Version 5.1
<#
  Loonie one-line installer.

  1. Installs Python 3.12 (via winget) if it's missing — Loonie's private local engine needs it.
  2. Downloads and launches the latest signed Loonie desktop installer.

  Everything else (engine setup, database, updates) is handled by the app itself on first launch,
  and you create your account inside the app — there are no config files to edit.

  Usage (from PowerShell):
    irm https://raw.githubusercontent.com/harshbhalodia/loonie/main/install.ps1 | iex
#>
$ErrorActionPreference = "Stop"

$RepoRaw = "https://raw.githubusercontent.com/harshbhalodia/loonie/main"

function Write-Step($msg) { Write-Host "`n== $msg ==" -ForegroundColor Cyan }

Write-Step "Checking for Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    # The Windows Store "python" alias exists even when Python isn't installed — make sure it runs.
    & python --version *> $null
    if ($LASTEXITCODE -ne 0) { $python = $null }
}
if (-not $python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Error "Python isn't installed and winget isn't available. Install Python 3.11+ from https://python.org/downloads/ (tick 'Add to PATH') and re-run this script."
        exit 1
    }
    Write-Host "Installing Python 3.12 via winget (this may take a minute)..." -ForegroundColor Yellow
    winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
} else {
    Write-Host "Found $(& python --version)" -ForegroundColor Green
}

Write-Step "Downloading the latest Loonie installer"
# Same manifest the in-app auto-updater reads, so this always grabs the current release.
$latest = Invoke-RestMethod -Uri "$RepoRaw/updater/latest.json"
$installerUrl = $latest.platforms.'windows-x86_64'.url
Write-Host "Latest version: $($latest.version)" -ForegroundColor Yellow
$installerPath = Join-Path $env:TEMP "Loonie-setup.exe"
Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

Write-Step "Launching installer"
Start-Process $installerPath -Wait

Write-Host "`nAll done! Launch Loonie from the Start menu and create your account on first launch." -ForegroundColor Green
