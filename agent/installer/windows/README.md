# Windows installer (MSI)

## Prerequisites

- **Windows 10 / 11** (64-bit) build host
- **Python 3.12+** in PATH
- **WiX Toolset 4 or 5** as a global dotnet tool:
  ```powershell
  dotnet tool install --global wix
  wix extension add WixToolset.UI.wixext
  wix extension add WixToolset.Util.wixext
  ```
  Verify: `wix --version` (should print 4.x or 5.x).
- **Internet** for the first build only (to download NSSM).

## Build

From the **repo root** in PowerShell:

```powershell
pwsh -File agent\installer\windows\build.ps1 -Version 0.1.0
```

This will:
1. `pip install -e ".[build,windows]"` inside `agent/` (PyInstaller, pywin32).
2. Run PyInstaller → `agent\dist\azurscan-agent.exe` (~25–35 MB).
3. Download NSSM 2.24 → `agent\installer\windows\nssm.exe` (one-time).
4. Compile WiX → `agent\dist\azur-scan-agent-0.1.0.msi` (~30–40 MB).

Re-builds skip steps 2 and 3 if artifacts already exist.

## What the MSI does

- Installs `azurscan-agent.exe` and `nssm.exe` into `C:\Program Files\AzurScan\`
- Creates `C:\ProgramData\AzurScan\` (logs/, config, outbox)
- Registers a Windows Service `AzurScanAgent` (auto-start, restart on failure)
- The service runs `azurscan-agent.exe run` under `LocalSystem`
- Stdout/stderr captured to `C:\ProgramData\AzurScan\logs\service.{out,err}.log`

## Post-install enrollment

The MSI does **not** enroll the agent — that's a separate step so you can
distribute the same MSI to any machine and supply the token via MDM/script:

```powershell
# Run as administrator
& "C:\Program Files\AzurScan\azurscan-agent.exe" enroll `
    --server https://api.your-company.com `
    --token evt_xxxxxxxxxxxxxxxxxxxx

# Restart the service to pick up new credentials
Restart-Service AzurScanAgent
```

## Code signing (optional)

```powershell
pwsh -File agent\installer\windows\build.ps1 `
    -Version 0.1.0 `
    -SignThumbprint "ABCDEF0123456789..."
```

Without signing, SmartScreen will warn users on first install until reputation
accrues. With an OV/EV cert (or **Microsoft Trusted Signing** which is ~$10/mo
and HSM-backed without physical token), the warning disappears within days.

## Uninstall

```powershell
msiexec /x "{6BE0A8C3-2D6A-4C8C-A2E5-91D6D9F1C7A1}" /quiet
```

Or from "Add or Remove Programs" → "Azur-Scan Agent". The uninstaller stops
the service via NSSM and removes it.
