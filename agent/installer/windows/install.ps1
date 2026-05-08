<#
.SYNOPSIS
  Portable installer for Azur-Scan Agent (no MSI; bypasses Group Policy
  DisableMSI restrictions).

.DESCRIPTION
  Copies files to C:\Program Files\AzurScan\, registers the AzurScanAgent
  Windows Service via WinSW, writes the server URL into config, and starts
  the service. Requires admin rights.

.PARAMETER ServerUrl
  Azur-Scan backend URL. If omitted, the script prompts.

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File install.ps1
  # Prompts for the URL.

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File install.ps1 -ServerUrl "http://10.0.20.143:8000"
#>
[CmdletBinding()]
param(
    [string]$ServerUrl = ""
)

$ErrorActionPreference = "Stop"

# ---- admin check ----
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "This script must be run as Administrator. Right-click PowerShell -> Run as administrator."
    exit 1
}

# ---- prompt for URL if missing ----
while (-not $ServerUrl) {
    $ServerUrl = Read-Host "Enter Azur-Scan server URL (example: http://10.0.20.143:8000)"
}
$ServerUrl = $ServerUrl.TrimEnd("/")

$InstallDir = "C:\Program Files\AzurScan"
$DataDir    = "C:\ProgramData\AzurScan"
$LogsDir    = "$DataDir\logs"
$ScriptDir  = $PSScriptRoot

Write-Host ""
Write-Host "Azur-Scan Agent - portable installer"
Write-Host "===================================="
Write-Host "Install dir : $InstallDir"
Write-Host "Data dir    : $DataDir"
Write-Host "Server URL  : $ServerUrl"
Write-Host ""

# ---- create dirs ----
foreach ($dir in @($InstallDir, $DataDir, $LogsDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created: $dir"
    }
}

# ---- stop and remove existing service if present ----
$svc = Get-Service -Name AzurScanAgent -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "Stopping existing service..."
    if ($svc.Status -eq "Running") { Stop-Service AzurScanAgent -Force -ErrorAction SilentlyContinue }
    if (Test-Path "$InstallDir\azurscan-service.exe") {
        & "$InstallDir\azurscan-service.exe" uninstall 2>$null | Out-Null
    } else {
        sc.exe delete AzurScanAgent | Out-Null
    }
    Start-Sleep -Seconds 2
}

# ---- copy files ----
Write-Host "Copying files..."
$files = @("azurscan-agent.exe", "azurscan-service.exe", "azurscan-service.xml")
foreach ($file in $files) {
    $src = Join-Path $ScriptDir $file
    if (-not (Test-Path $src)) {
        Write-Error "Missing file: $src - extract the ZIP first."
        exit 1
    }
    Copy-Item $src "$InstallDir\$file" -Force
    Write-Host "  Copied: $file"
}

# ---- write config (server URL) ----
Write-Host "Writing config..."
& "$InstallDir\azurscan-agent.exe" set-config --server $ServerUrl
if ($LASTEXITCODE -ne 0) {
    Write-Error "set-config failed (exit $LASTEXITCODE)"
    exit 1
}

# ---- register service via WinSW ----
Write-Host "Registering Windows Service..."
& "$InstallDir\azurscan-service.exe" install
if ($LASTEXITCODE -ne 0) {
    Write-Error "WinSW install failed (exit $LASTEXITCODE)"
    exit 1
}

# Service recovery: restart on failure
sc.exe failure AzurScanAgent reset= 86400 actions= restart/30000/restart/60000/restart/300000 | Out-Null

# ---- start service ----
Write-Host "Starting service..."
Start-Service AzurScanAgent
$svc = Get-Service AzurScanAgent
Write-Host "Service status: $($svc.Status)"

Write-Host @"

============================================================
  Installation complete.
  The agent will auto-register and appear in the admin UI
  within about 30 seconds.

  Logs:    $LogsDir
  Status:  & "$InstallDir\azurscan-agent.exe" status
============================================================

"@
