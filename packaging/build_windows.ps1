#Requires -Version 5.1
<#
.SYNOPSIS
    Builds the PhotoSleuth Windows application and installer.

.DESCRIPTION
    Run from the repository root in a PowerShell prompt:

        .\packaging\build_windows.ps1

    Steps:
      1. Creates/uses a virtual environment in .venv
      2. Installs PhotoSleuth plus its build dependencies
      3. Regenerates the logo and .ico
      4. Runs PyInstaller  -> dist\PhotoSleuth\
      5. Runs Inno Setup   -> dist\installer\  (skipped if iscc is not found)

.PARAMETER SkipInstaller
    Build the application folder only.
#>

[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> PhotoSleuth Windows build" -ForegroundColor Cyan
Write-Host "    Repository: $root"

if ($Clean) {
    Write-Host "==> Cleaning previous build output"
    foreach ($dir in @('build', 'dist')) {
        if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
    }
}

$venv = Join-Path $root '.venv'
if (-not (Test-Path $venv)) {
    Write-Host "==> Creating virtual environment"
    python -m venv $venv
}
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Virtual environment is missing $python" }

Write-Host "==> Installing dependencies"
& $python -m pip install --upgrade pip --quiet
& $python -m pip install -e ".[build,gui]" --quiet
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }

Write-Host "==> Syncing version numbers"
& $python tools\sync_version.py
if ($LASTEXITCODE -ne 0) { throw "Version sync failed" }

Write-Host "==> Regenerating icons"
& $python tools\make_assets.py
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }

Write-Host "==> Running PyInstaller"
& $python -m PyInstaller packaging\photosleuth.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$appExe = Join-Path $root 'dist\PhotoSleuth\PhotoSleuth.exe'
if (-not (Test-Path $appExe)) { throw "Build did not produce $appExe" }

$size = [math]::Round((Get-ChildItem 'dist\PhotoSleuth' -Recurse |
        Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host "==> Application built: dist\PhotoSleuth ($size MB)" -ForegroundColor Green

if ($SkipInstaller) {
    Write-Host "==> Skipping installer (-SkipInstaller)"
    exit 0
}

$iscc = $null
foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
    if (Test-Path $candidate) { $iscc = $candidate; break }
}
if (-not $iscc) { $iscc = (Get-Command iscc -ErrorAction SilentlyContinue)?.Source }

if (-not $iscc) {
    Write-Warning "Inno Setup (ISCC.exe) not found - skipping the installer."
    Write-Warning "Install it from https://jrsoftware.org/isdl.php and re-run."
    exit 0
}

Write-Host "==> Running Inno Setup"
& $iscc packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

Get-ChildItem 'dist\installer\*.exe' | ForEach-Object {
    $mb = [math]::Round($_.Length / 1MB, 1)
    Write-Host "==> Installer: $($_.FullName) ($mb MB)" -ForegroundColor Green
}
