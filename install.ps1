#requires -Version 5.1
<#
  Loonie one-click onboarding script.

  Run this on a machine that has never touched Loonie before. It will:
    1. Install Python (via winget) if it's missing.
    2. Set up the Loonie backend (venv + dependencies) under %LOCALAPPDATA%\Loonie\backend.
    3. Create config/config.yaml from the example template (with a fresh random JWT secret).
    4. Download and launch the current Loonie desktop installer.

  Only downloads the backend source files + the current installer - never the whole repo
  (which also holds every past installer build) - so this stays fast even as releases pile up.

  Usage (from PowerShell):
    irm https://raw.githubusercontent.com/harshbhalodia/loonie/main/install.ps1 | iex
#>
$ErrorActionPreference = "Stop"

$Owner = "harshbhalodia"
$Repo = "loonie"
$RepoRaw = "https://raw.githubusercontent.com/$Owner/$Repo/main"
$ApiBase = "https://api.github.com/repos/$Owner/$Repo/contents"
$LoonieHome = Join-Path $env:LOCALAPPDATA "Loonie"
$BackendHome = Join-Path $LoonieHome "backend"

function Write-Step($msg) { Write-Host "`n== $msg ==" -ForegroundColor Cyan }

# Recursively downloads a folder from the repo via the GitHub Contents API, so install only
# pulls the handful of backend source files instead of the entire repo (installers included).
function Get-GithubFolder($apiPath, $destDir) {
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $entries = Invoke-RestMethod -Uri "$ApiBase/$apiPath" -Headers @{ "User-Agent" = "loonie-install" }
    foreach ($entry in $entries) {
        if ($entry.type -eq "dir") {
            Get-GithubFolder "$apiPath/$($entry.name)" (Join-Path $destDir $entry.name)
        } else {
            Invoke-WebRequest -Uri $entry.download_url -OutFile (Join-Path $destDir $entry.name)
        }
    }
}

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
if (Test-Path $BackendHome) { Remove-Item $BackendHome -Recurse -Force }
Get-GithubFolder "backend" $BackendHome

$configDir = Join-Path $LoonieHome "config"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$configExampleCopy = Join-Path $configDir "config.example.yaml"
Invoke-WebRequest -Uri "$RepoRaw/config/config.example.yaml" -OutFile $configExampleCopy

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
# Reads updater/latest.json instead of a hardcoded filename, so this always grabs whichever
# version is currently published - no need to edit this script for every new release.
$latest = Invoke-RestMethod -Uri "$RepoRaw/updater/latest.json"
$installerUrl = $latest.platforms.'windows-x86_64'.url
Write-Host "Latest version: $($latest.version)" -ForegroundColor Yellow
$installerPath = Join-Path $env:TEMP "Loonie-setup.exe"
Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath
Write-Host "Launching installer..." -ForegroundColor Green
Start-Process $installerPath -Wait

Write-Host "`nAll done! Launch Loonie from the Start Menu." -ForegroundColor Green
Write-Host "Log in with admin@example.com / change-me (see $configYaml)." -ForegroundColor Green

