<#
.SYNOPSIS
  Packages the Azur-Scan Agent into a ZIP archive ready for deployment.

.DESCRIPTION
  Builds the agent .exe (or reuses existing), downloads WinSW if needed,
  then zips everything into agent/dist/azur-scan-agent-<version>.zip.

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File agent\installer\windows\package.ps1 -Version 0.1.0
  pwsh -ExecutionPolicy Bypass -File agent\installer\windows\package.ps1 -Version 0.1.0 -SkipExeBuild
#>
[CmdletBinding()]
param(
    [string]$Version = "0.1.0",
    [switch]$SkipExeBuild
)

$ErrorActionPreference = "Stop"
$RepoRoot     = Resolve-Path "$PSScriptRoot\..\..\.."
$AgentDir     = Join-Path $RepoRoot "agent"
$InstallerDir = Join-Path $AgentDir "installer\windows"
$DistDir      = Join-Path $AgentDir "dist"
$AgentExe     = Join-Path $DistDir "azurscan-agent.exe"
$WinSwExe     = Join-Path $InstallerDir "azurscan-service.exe"
$ZipOut       = Join-Path $DistDir "azur-scan-agent-$Version.zip"

if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }

Write-Host "Azur-Scan Agent packager"
Write-Host "Version: $Version"

# ---------------------------------------------------------------------------
# 1. Build agent.exe
# ---------------------------------------------------------------------------
if (-not $SkipExeBuild) {
    Write-Host "`n[1/3] Building agent.exe with PyInstaller..."
    Push-Location $AgentDir
    try {
        python -m pip install "pyinstaller>=6.5" --quiet
        python -m pip install -e "." --quiet
        python build\build.py
        if (-not (Test-Path $AgentExe)) { throw "PyInstaller did not produce $AgentExe" }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[1/3] Skipping exe build (-SkipExeBuild)."
    if (-not (Test-Path $AgentExe)) { throw "$AgentExe missing. Run without -SkipExeBuild first." }
}

# ---------------------------------------------------------------------------
# 2. Download WinSW
# ---------------------------------------------------------------------------
if (-not (Test-Path $WinSwExe)) {
    Write-Host "`n[2/3] Downloading WinSW from GitHub..."
    Invoke-WebRequest "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe" `
        -OutFile $WinSwExe -UseBasicParsing
    Write-Host "    Saved: $WinSwExe"
} else {
    Write-Host "`n[2/3] WinSW already present."
}

# ---------------------------------------------------------------------------
# 3. Create ZIP
# ---------------------------------------------------------------------------
Write-Host "`n[3/3] Creating ZIP..."

$staging = Join-Path $env:TEMP "azurscan-pkg-$Version"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null

$MsiOut    = Join-Path $DistDir "azur-scan-agent-$Version.msi"
$SetupExe  = Join-Path $DistDir "azur-scan-agent-setup.exe"
$filesToInclude = @{
    $AgentExe                                                    = "azurscan-agent.exe"
    $WinSwExe                                                    = "azurscan-service.exe"
    "$InstallerDir\azurscan-service.xml"                         = "azurscan-service.xml"
    "$InstallerDir\install.ps1"                                  = "install.ps1"
    "$InstallerDir\uninstall.ps1"                                = "uninstall.ps1"
    "$InstallerDir\install-azurscan.cmd"                         = "install-azurscan.cmd"
}
# Bundle the MSI and the GUI setup wizard too, when available — gives users
# every install path in one ZIP. Order of preference at runtime:
#   azur-scan-agent-setup.exe  — friendly GUI, asks only for URL (recommended)
#   install-azurscan.cmd       — wraps msiexec with an interactive URL prompt
#   azur-scan-agent-X.Y.msi    — for silent / SCCM / Intune deployments
#   install.ps1                — portable, bypasses Windows Installer policy
if (Test-Path $MsiOut)   { $filesToInclude[$MsiOut]   = "azur-scan-agent-$Version.msi" }
if (Test-Path $SetupExe) { $filesToInclude[$SetupExe] = "azur-scan-agent-setup.exe" }

foreach ($src in $filesToInclude.Keys) {
    $dst = Join-Path $staging $filesToInclude[$src]
    Copy-Item $src $dst
}

# Write a README.txt into the zip
@"
Azur-Scan Agent $Version - Windows
====================================

The agent does NOT need an enrollment token. Just supply the server URL
during install; on first run the service registers itself automatically.

PREFERRED PATH (most users) - GUI wizard:
  1. Right-click azur-scan-agent-setup.exe
  2. Select "Run as administrator"
  3. Confirm the pre-filled server URL (or change it)
  4. Click "Install & Enroll"

ALTERNATIVE - CMD wrapper around the MSI:
  1. Right-click install-azurscan.cmd
  2. Select "Run as administrator"
  3. When prompted, type the server URL, e.g. http://10.0.20.143:8000

SILENT INSTALL (Intune / SCCM / scripts):
  msiexec /i azur-scan-agent-$Version.msi SERVER_URL="http://10.0.20.143:8000" /qn /norestart

PORTABLE / NO-MSI INSTALL (when Group Policy blocks msiexec):
  Open PowerShell as Administrator and run:
    pwsh -ExecutionPolicy Bypass -File install.ps1
  Or with URL pre-filled:
    pwsh -ExecutionPolicy Bypass -File install.ps1 -ServerUrl "http://10.0.20.143:8000"

UNINSTALL:
  msiexec /x ``{6BE0A8C3-2D6A-4C8C-A2E5-91D6D9F1C7A1}``  ``# for MSI installs
  pwsh -ExecutionPolicy Bypass -File uninstall.ps1      ``# for portable installs

VERIFY:
  Get-Service AzurScanAgent
  & "C:\Program Files\AzurScan\azurscan-agent.exe" status

Logs:   C:\ProgramData\AzurScan\logs\
Config: C:\ProgramData\AzurScan\config.yaml
"@ | Set-Content "$staging\README.txt" -Encoding UTF8

if (Test-Path $ZipOut) { Remove-Item $ZipOut }
Compress-Archive -Path "$staging\*" -DestinationPath $ZipOut

Remove-Item $staging -Recurse -Force

$sizeMB = (Get-Item $ZipOut).Length / 1MB
Write-Host ("`nDone: {0}  ({1:N1} MB)" -f $ZipOut, $sizeMB)
Write-Host "Copy this ZIP to the target laptop, extract, and run install.ps1 as Administrator."
