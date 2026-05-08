# macOS installer (.pkg + .dmg)

## Why both `.pkg` and `.dmg`

For a **system daemon** like Azur-Scan Agent, you need the `installer(8)`
framework to register a LaunchDaemon at `/Library/LaunchDaemons/`. That requires
a `.pkg`, not just a drag-to-Applications `.dmg`.

But end users expect a `.dmg` for downloads — so we ship the `.pkg` *inside* a
`.dmg`. The user mounts the DMG, double-clicks the .pkg, and macOS Installer
takes over with proper privilege escalation.

```
azur-scan-agent-0.1.0.dmg                       ← what users download
└── Azur-Scan Agent.pkg                         ← what they double-click
    └── postinstall → launchctl bootstrap …     ← what registers the service
```

## Prerequisites

- **macOS 12+** build host (cross-compile from Windows is **not possible** —
  `pkgbuild`/`productbuild`/`hdiutil`/`codesign` are macOS-only)
- **Xcode Command Line Tools**: `xcode-select --install`
- **Python 3.12+**

## Build (unsigned, dev)

```bash
bash agent/installer/macos/build.sh
```

Produces:

- `agent/dist/azur-scan-agent-0.1.0.pkg`
- `agent/dist/azur-scan-agent-0.1.0.dmg`

When a user opens the unsigned `.pkg`, Gatekeeper will refuse to launch it.
Workaround for the user:

> Right-click the `.pkg` → **Open** → **Open** in the warning dialog.
> Or: System Settings → Privacy & Security → "Open Anyway".

This is fine for internal pilot. Not fine for production.

## Build (signed + notarized, production)

```bash
# 1. Pre-store an app-specific password for notarytool (one-time, per host):
xcrun notarytool store-credentials azurscan-notary \
    --apple-id you@company.com \
    --team-id  ABCDE12345 \
    --password "abcd-efgh-ijkl-mnop"   # app-specific password

# 2. Build with signing + notarization:
bash agent/installer/macos/build.sh \
     --version 0.1.0 \
     --sign-app "Developer ID Application: Acme, Inc. (ABCDE12345)" \
     --sign-pkg "Developer ID Installer:   Acme, Inc. (ABCDE12345)" \
     --notarize-keychain-profile azurscan-notary
```

Apple Developer Program subscription ($99/yr) gives you:
- "Developer ID Application" — for signing the agent binary
- "Developer ID Installer"   — for signing the .pkg

Without these, Gatekeeper warnings are unavoidable.

## What the installer does

1. Copies the agent binary to `/usr/local/azurscan/bin/azurscan-agent`
2. Drops the LaunchDaemon plist at `/Library/LaunchDaemons/com.azurscan.agent.plist`
3. `launchctl bootstrap system <plist>` — registers the daemon
4. `launchctl kickstart -k system/com.azurscan.agent` — starts it

## Post-install enrollment

```bash
sudo /usr/local/azurscan/bin/azurscan-agent enroll \
     --server https://api.your-company.com \
     --token  evt_xxxxxxxxxxxxxxxx

# Restart the daemon to pick up new credentials
sudo launchctl kickstart -k system/com.azurscan.agent
```

Credentials go into the **System Keychain** (service `com.azurscan.agent`).

## Uninstall

macOS `.pkg` doesn't ship with a native uninstaller. Use the helper:

```bash
sudo bash /path/to/agent/installer/macos/preuninstall
```

Or manually:

```bash
sudo launchctl bootout system /Library/LaunchDaemons/com.azurscan.agent.plist
sudo rm /Library/LaunchDaemons/com.azurscan.agent.plist
sudo rm -rf /usr/local/azurscan
sudo rm -rf "/Library/Application Support/AzurScan"
sudo rm -rf /Library/Logs/AzurScan
sudo pkgutil --forget com.azurscan.agent
```
