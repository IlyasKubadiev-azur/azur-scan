<#
.SYNOPSIS
  Build the Azur-Scan Agent MSI installer for Windows.

.DESCRIPTION
  End-to-end build script:
    1. Builds the agent .exe with PyInstaller (if not already built).
    2. Downloads WinSW (Windows Service Wrapper) from GitHub.
    3. Compiles azur-scan.wxs into azur-scan-agent-<version>.msi using WiX 4+.

.REQUIREMENTS
  - Python 3.12+
  - WiX Toolset 4+    (`dotnet tool install --global wix`)
  - Internet (one-time, to fetch WinSW)

.EXAMPLE
  pwsh -File agent\installer\windows\build.ps1 -Version 0.1.0
#>
[CmdletBinding()]
param(
    [string]$Version = "0.1.0",
    [switch]$SkipExeBuild,
    [string]$SignThumbprint = ""   # optional code-signing cert thumbprint
)

$ErrorActionPreference = "Stop"
$RepoRoot     = Resolve-Path "$PSScriptRoot\..\..\.."
$AgentDir     = Join-Path $RepoRoot "agent"
$InstallerDir = Join-Path $AgentDir "installer\windows"
$DistDir      = Join-Path $AgentDir "dist"
$WinSwExe     = Join-Path $InstallerDir "azurscan-service.exe"
$AgentExe     = Join-Path $DistDir "azurscan-agent.exe"
$WxsFile      = Join-Path $InstallerDir "azur-scan.wxs"
$MsiOut       = Join-Path $DistDir ("azur-scan-agent-{0}.msi" -f $Version)

Write-Host "Repo root:    $RepoRoot"
Write-Host "Version:      $Version"

# ---------------------------------------------------------------------------
# 1. Build the .exe via PyInstaller
# ---------------------------------------------------------------------------
if (-not $SkipExeBuild) {
    Write-Host "`n[1/3] Building agent .exe via PyInstaller..."
    Push-Location $AgentDir
    try {
        python -m pip install --upgrade pip *> $null
        python -m pip install -e ".[build,windows]"
        python build\build.py
        if (-not (Test-Path $AgentExe)) {
            throw "PyInstaller did not produce $AgentExe"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[1/3] Skipping .exe build (-SkipExeBuild)."
    if (-not (Test-Path $AgentExe)) {
        throw "$AgentExe is missing — run without -SkipExeBuild first."
    }
}

# ---------------------------------------------------------------------------
# 2. Fetch WinSW if missing (Windows Service Wrapper — GitHub releases)
# ---------------------------------------------------------------------------
if (-not (Test-Path $WinSwExe)) {
    Write-Host "`n[2/3] WinSW not found — downloading from GitHub..."
    $WinSwUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
    try {
        Invoke-WebRequest $WinSwUrl -OutFile $WinSwExe -UseBasicParsing
        Write-Host "    WinSW saved to $WinSwExe"
    } catch {
        throw "Failed to download WinSW: $_"
    }
} else {
    Write-Host "`n[2/3] WinSW already present at $WinSwExe"
}

# ---------------------------------------------------------------------------
# 3. Compile MSI with WiX
# ---------------------------------------------------------------------------
Write-Host "`n[3/3] Building MSI with WiX..."

# Detect WiX install location if not on PATH (e.g. installed via `dotnet tool
# install --global wix` but PATH not refreshed in current shell).
$wixCmd = (Get-Command wix -ErrorAction SilentlyContinue).Source
if (-not $wixCmd) {
    $candidate = Join-Path $env:USERPROFILE ".dotnet\tools\wix.exe"
    if (Test-Path $candidate) { $wixCmd = $candidate }
}
if (-not $wixCmd) {
    throw "wix not found on PATH or in ~/.dotnet/tools. Install: dotnet tool install --global wix"
}
Write-Host "    Using WiX at: $wixCmd"

# WiX 7+ requires accepting the OSMF EULA. Pass --acceptEula per-invocation
# so the script doesn't silently install a persistent acceptance file. To
# accept once globally instead, run:  wix eula accept wix7
# Note: requires `wix eula accept wix7` to have been run once on this profile.
# build.ps1 doesn't auto-accept — that's a deliberate one-time legal action.
$wixArgs = @(
    "build",
    $WxsFile,
    "-d", "AgentExeSource=$AgentExe",
    "-d", "WinSwSource=$WinSwExe",
    "-d", "InstallerDir=$InstallerDir",
    "-d", "Version=$Version",
    "-o", $MsiOut
)
& $wixCmd @wixArgs
if ($LASTEXITCODE -ne 0) { throw "WiX build failed (exit $LASTEXITCODE)" }

Write-Host "`nBuilt: $MsiOut"
$msiSize = (Get-Item $MsiOut).Length / 1MB
Write-Host ("Size:  {0:N1} MB" -f $msiSize)

# ---------------------------------------------------------------------------
# Optional: code signing
# ---------------------------------------------------------------------------
if ($SignThumbprint) {
    Write-Host "`nSigning MSI with thumbprint $SignThumbprint..."
    & signtool sign /sha1 $SignThumbprint `
        /tr "http://timestamp.digicert.com" /td sha256 /fd sha256 `
        $MsiOut
    if ($LASTEXITCODE -ne 0) { throw "signtool failed" }
    Write-Host "Signed."
} else {
    Write-Host "`nNote: MSI is unsigned. SmartScreen will warn end users until reputation accrues."
    Write-Host "      See -SignThumbprint to sign with a code-signing certificate."
}
