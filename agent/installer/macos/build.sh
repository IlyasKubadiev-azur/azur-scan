#!/bin/bash
# Build the Azur-Scan Agent .pkg + .dmg for macOS.
#
# Output:
#   agent/dist/azur-scan-agent-<version>.pkg
#   agent/dist/azur-scan-agent-<version>.dmg   (drag-mountable disk image
#                                                containing the .pkg)
#
# Requirements:
#   - macOS 12+ build host
#   - Xcode Command Line Tools (provides pkgbuild, productbuild, hdiutil, codesign)
#   - Python 3.12+
#
# Usage:
#   bash agent/installer/macos/build.sh                      # unsigned (dev)
#   bash agent/installer/macos/build.sh -v 0.1.0 \
#        --sign-pkg "Developer ID Installer: Acme, Inc."     # signed
#        --sign-app "Developer ID Application: Acme, Inc."
#        --notarize-keychain-profile  azurscan-notary

set -euo pipefail

VERSION="0.1.0"
SIGN_PKG=""
SIGN_APP=""
NOTARIZE_PROFILE=""
SKIP_BUILD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -v|--version)              VERSION="$2"; shift 2;;
    --sign-pkg)                SIGN_PKG="$2"; shift 2;;
    --sign-app)                SIGN_APP="$2"; shift 2;;
    --notarize-keychain-profile) NOTARIZE_PROFILE="$2"; shift 2;;
    --skip-build)              SKIP_BUILD=1; shift;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
AGENT_DIR="$REPO_ROOT/agent"
INSTALLER_DIR="$AGENT_DIR/installer/macos"
DIST_DIR="$AGENT_DIR/dist"
BUILD_TMP="$AGENT_DIR/build/_macos_pkg"
PAYLOAD_DIR="$BUILD_TMP/payload"
SCRIPTS_DIR="$BUILD_TMP/scripts"
RESOURCES_DIR="$INSTALLER_DIR/Resources"

PKG_COMPONENT="$BUILD_TMP/azurscan-agent-component.pkg"
PKG_OUT="$DIST_DIR/azur-scan-agent-${VERSION}.pkg"
DMG_OUT="$DIST_DIR/azur-scan-agent-${VERSION}.dmg"
DMG_STAGE="$BUILD_TMP/dmg-stage"

echo "Repo root:    $REPO_ROOT"
echo "Version:      $VERSION"

# ---------------------------------------------------------------------------
# 1. Build the agent binary via PyInstaller
# ---------------------------------------------------------------------------
if [ "$SKIP_BUILD" -eq 0 ]; then
  echo
  echo "[1/4] Building agent binary via PyInstaller..."
  cd "$AGENT_DIR"
  python3 -m pip install --upgrade pip > /dev/null
  python3 -m pip install -e ".[build]"
  python3 build/build.py
fi

AGENT_BIN="$AGENT_DIR/dist/azurscan-agent"
if [ ! -f "$AGENT_BIN" ]; then
  echo "ERROR: $AGENT_BIN not found"
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. Stage payload
# ---------------------------------------------------------------------------
echo
echo "[2/4] Staging payload..."
rm -rf "$BUILD_TMP"
mkdir -p "$PAYLOAD_DIR/usr/local/azurscan/bin"
mkdir -p "$PAYLOAD_DIR/Library/LaunchDaemons"
mkdir -p "$SCRIPTS_DIR"
mkdir -p "$DIST_DIR"

cp "$AGENT_BIN" "$PAYLOAD_DIR/usr/local/azurscan/bin/azurscan-agent"
chmod 755 "$PAYLOAD_DIR/usr/local/azurscan/bin/azurscan-agent"

cp "$INSTALLER_DIR/com.azurscan.agent.plist" "$PAYLOAD_DIR/Library/LaunchDaemons/"
chmod 644 "$PAYLOAD_DIR/Library/LaunchDaemons/com.azurscan.agent.plist"

cp "$INSTALLER_DIR/postinstall" "$SCRIPTS_DIR/postinstall"
chmod 755 "$SCRIPTS_DIR/postinstall"

# Optionally sign the binary
if [ -n "$SIGN_APP" ]; then
  echo "    codesign'ing agent binary..."
  codesign --force --options runtime --timestamp \
           --sign "$SIGN_APP" \
           "$PAYLOAD_DIR/usr/local/azurscan/bin/azurscan-agent"
fi

# ---------------------------------------------------------------------------
# 3. Build component .pkg + product .pkg
# ---------------------------------------------------------------------------
echo
echo "[3/4] Building .pkg..."
pkgbuild \
  --root "$PAYLOAD_DIR" \
  --identifier com.azurscan.agent \
  --version "$VERSION" \
  --install-location / \
  --scripts "$SCRIPTS_DIR" \
  "$PKG_COMPONENT"

PRODUCTBUILD_ARGS=(
  --distribution "$INSTALLER_DIR/distribution.xml"
  --resources    "$RESOURCES_DIR"
  --package-path "$BUILD_TMP"
  "$PKG_OUT"
)

if [ -n "$SIGN_PKG" ]; then
  PRODUCTBUILD_ARGS=(--sign "$SIGN_PKG" --timestamp "${PRODUCTBUILD_ARGS[@]}")
fi

(cd "$BUILD_TMP" && productbuild "${PRODUCTBUILD_ARGS[@]}")

echo "    Built: $PKG_OUT"

# Optional: notarize
if [ -n "$NOTARIZE_PROFILE" ]; then
  echo "    Notarizing..."
  xcrun notarytool submit "$PKG_OUT" --keychain-profile "$NOTARIZE_PROFILE" --wait
  xcrun stapler staple "$PKG_OUT"
fi

# ---------------------------------------------------------------------------
# 4. Wrap into a .dmg
# ---------------------------------------------------------------------------
echo
echo "[4/4] Packaging .dmg..."
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE"
cp "$PKG_OUT" "$DMG_STAGE/Azur-Scan Agent.pkg"

# Add a small README for the user who mounts the DMG
cat > "$DMG_STAGE/README.txt" <<EOF
Azur-Scan Agent ${VERSION}

Double-click "Azur-Scan Agent.pkg" to install.

After installation, enroll the device with:

    sudo /usr/local/azurscan/bin/azurscan-agent enroll \\
         --server https://your.azurscan.server \\
         --token  evt_...

    sudo launchctl kickstart -k system/com.azurscan.agent

Logs: /Library/Logs/AzurScan/
EOF

rm -f "$DMG_OUT"
hdiutil create \
  -volname "Azur-Scan Agent ${VERSION}" \
  -srcfolder "$DMG_STAGE" \
  -ov \
  -format UDZO \
  "$DMG_OUT" >/dev/null

echo "    Built: $DMG_OUT"

if [ -n "$SIGN_APP" ]; then
  echo "    Signing DMG..."
  codesign --force --sign "$SIGN_APP" --timestamp "$DMG_OUT"
fi

if [ -n "$NOTARIZE_PROFILE" ]; then
  echo "    Notarizing DMG..."
  xcrun notarytool submit "$DMG_OUT" --keychain-profile "$NOTARIZE_PROFILE" --wait
  xcrun stapler staple "$DMG_OUT"
fi

echo
echo "Done."
ls -lh "$PKG_OUT" "$DMG_OUT" || true
