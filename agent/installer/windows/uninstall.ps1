<#
.SYNOPSIS
  Uninstalls Azur-Scan Agent.
.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File uninstall.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Run as Administrator."
    exit 1
}

$InstallDir = "C:\Program Files\AzurScan"

$svc = Get-Service -Name AzurScanAgent -ErrorAction SilentlyContinue
if ($svc) {
    if ($svc.Status -eq "Running") {
        Write-Host "Stopping service..."
        Stop-Service AzurScanAgent -Force
    }
    Write-Host "Unregistering service..."
    & "$InstallDir\azurscan-service.exe" uninstall
}

Write-Host "Removing files..."
if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }

Write-Host "Done. Data and logs preserved at C:\ProgramData\AzurScan\"
Write-Host "Remove manually if needed: Remove-Item 'C:\ProgramData\AzurScan' -Recurse -Force"
