#requires -Version 5.1
<#
  Loonie one-click onboarding script.

  Run this on a machine that has never touched Loonie before. It will:
    1. Install Python (via winget) if it's missing.
    2. Set up the Loonie backend (venv + dependencies) under %LOCALAPPDATA%\Loonie\backend.
    3. Create config/config.yaml from the example template (with a fresh random JWT secret).
    4. Download and launch the Loonie desktop installer.

  Usage (from PowerShell):
    irm https://raw.githubusercontent.com/harshbhalodia/loonie/main/install.ps1 | iex
#>
$ErrorActionPreference = "Stop"

$RepoRaw = "https://raw.githubusercontent.com/harshbhalodia/loonie/main"
$RepoZip = "https://github.com/harshbhalodia/loonie/archive/refs/heads/main.zip"
$LoonieHome = Join-Path $env:LOCALAPPDATA "Loonie"
$BackendHome = Join-Path $LoonieHome "backend"

function Write-Step($msg) { Write-Host "`n== $msg ==" -ForegroundColor Cyan }

Write-Step "Checking for Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Error "Python isn't installed and winget isn't available. Please install Python 3.11+ from https://python.org/downloads/ and re-run this script."
        exit 1
    }
    Write-Host "Python not found - installing via winget (this may take a minute)..." -ForegroundColor Yellow
    winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    # winget just installed it - refresh PATH for this session.
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Step "Downloading Loonie backend source"
New-Item -ItemType Directory -Force -Path $LoonieHome | Out-Null
$zipPath = Join-Path $env:TEMP "loonie-main.zip"
Invoke-WebRequest -Uri $RepoZip -OutFile $zipPath
$extractDir = Join-Path $env:TEMP "loonie-extract"
if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force }
Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
$extractedBackend = Join-Path $extractDir "loonie-main\backend"
$extractedConfigExample = Join-Path $extractDir "loonie-main\config\config.example.yaml"

if (Test-Path $BackendHome) { Remove-Item $BackendHome -Recurse -Force }
Copy-Item $extractedBackend $BackendHome -Recurse -Force

$configDir = Join-Path $LoonieHome "config"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$configExampleCopy = Join-Path $configDir "config.example.yaml"
Copy-Item $extractedConfigExample $configExampleCopy -Force

Remove-Item $zipPath, $extractDir -Recurse -Force

Write-Step "Setting up Python virtual environment"
python -m venv (Join-Path $BackendHome ".venv")
$pythonExe = Join-Path $BackendHome ".venv\Scripts\python.exe"
& $pythonExe -m pip install --upgrade pip -q
& $pythonExe -m pip install -r (Join-Path $BackendHome "requirements.txt") -q

Write-Step "Creating configuration"
$configYaml = Join-Path $configDir "config.yaml"
if (-not (Test-Path $configYaml)) {
    Copy-Item $configExampleCopy $configYaml
    # Each install gets its own random JWT secret instead of the shared example placeholder.
    $secret = -join ((1..64) | ForEach-Object { "{0:x}" -f (Get-Random -Maximum 16) })
    (Get-Content $configYaml) -replace "change-me-to-a-long-random-string", $secret | Set-Content $configYaml
    Write-Host "Created $configYaml" -ForegroundColor Yellow
    Write-Host "Default login: admin@example.com / change-me - change this after your first login." -ForegroundColor Yellow
}

Write-Step "Running database migrations"
Push-Location $BackendHome
& $pythonExe -m alembic upgrade head
Pop-Location

Write-Step "Downloading the Loonie desktop app"
$installerPath = Join-Path $env:TEMP "Loonie-setup.exe"
Invoke-WebRequest -Uri "$RepoRaw/installer/Loonie_0.1.0_x64-setup.exe" -OutFile $installerPath
Write-Host "Launching installer..." -ForegroundColor Green
Start-Process $installerPath -Wait

Write-Host "`nAll done! Launch Loonie from the Start Menu." -ForegroundColor Green
Write-Host "Log in with admin@example.com / change-me (see $configYaml)." -ForegroundColor Green
