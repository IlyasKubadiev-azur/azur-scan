# Azur-Scan Agent

Cross-platform endpoint inventory agent (Windows + macOS).

## Quick start (no installer — local testing)

```bash
cd agent
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[windows]"                          # on Windows; just -e . on macOS

# Tokenless enrollment — any reachable machine can register
python -m azurscan_agent enroll --server http://localhost:8000

python -m azurscan_agent status         # see what got stored
python -m azurscan_agent scan-now       # run one scan and exit
python -m azurscan_agent run            # run the main loop (Ctrl+C to stop)
```

After `scan-now` or `run`, the device shows up in `/admin/assets/asset/`.

## Layout

```
agent/
├── azurscan_agent/        Python package (entrypoint: __main__.py / cli.py)
│   ├── cli.py             enroll / run / scan-now / status / uninstall
│   ├── runtime.py         heartbeat + scan + outbox flush loop
│   ├── transport.py       HTTP client + token refresh + SQLite outbox
│   ├── collectors.py      cross-platform fact collectors
│   ├── machine.py         stable per-device id + hostname
│   ├── secrets_store.py   DPAPI (Win) / Keychain (Mac) / file (Linux)
│   ├── config.py          paths + YAML config
│   └── logging_setup.py   rotating file + console
├── build/
│   ├── azurscan-agent.spec    PyInstaller spec
│   └── build.py               cross-platform driver
├── installer/
│   ├── windows/           WiX 4 source + build.ps1 + NSSM glue
│   └── macos/             pkgbuild + DMG wrapper + LaunchDaemon plist
└── pyproject.toml
```

## Build installers

### Windows (.msi)

On a Windows 10/11 host with WiX 4+ and Python 3.12+:

```powershell
pwsh -File agent\installer\windows\build.ps1 -Version 0.1.0
# → agent\dist\azur-scan-agent-0.1.0.msi
```

See [installer/windows/README.md](installer/windows/README.md) for details.

### macOS (.pkg + .dmg)

On a macOS 12+ host with Xcode CLI tools and Python 3.12+:

```bash
bash agent/installer/macos/build.sh
# → agent/dist/azur-scan-agent-0.1.0.pkg
# → agent/dist/azur-scan-agent-0.1.0.dmg
```

See [installer/macos/README.md](installer/macos/README.md) for details on
signing and notarization.

## Storage layout on installed hosts

| Path | Windows | macOS |
|---|---|---|
| Binary | `C:\Program Files\AzurScan\azurscan-agent.exe` | `/usr/local/azurscan/bin/azurscan-agent` |
| Config | `C:\ProgramData\AzurScan\config.yaml` | `/Library/Application Support/AzurScan/config.yaml` |
| Outbox | `C:\ProgramData\AzurScan\outbox.sqlite3` | `/Library/Application Support/AzurScan/outbox.sqlite3` |
| Logs | `C:\ProgramData\AzurScan\logs\` | `/Library/Logs/AzurScan/` |
| Credentials | DPAPI blob (`credentials.bin`) | System Keychain (`com.azurscan.agent`) |
| Service | Windows Service `AzurScanAgent` (via NSSM) | LaunchDaemon `com.azurscan.agent` |

## What's NOT in the agent (deliberately, for MVP)

- Self-update — adding requires backend channel + signed update bundles
- Software inventory (installed programs / packages)
- Patch detection
- Remote command execution beyond `rescan`
- mTLS — auth is HS256-signed JWT for now
- GUI / system tray icon — pure background daemon
