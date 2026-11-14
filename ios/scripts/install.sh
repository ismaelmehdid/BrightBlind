#!/usr/bin/env bash
# Sign an IPA with an Apple ID and install it on the iPhone plugged in over USB.
# Usage: ios/scripts/install.sh [wifi|ble] [release-tag]
#   wifi  (default) Hotspot Configuration entitlement included: glasses Wi-Fi streaming.
#         If the signing account cannot carry that entitlement the app will not install or
#         will not launch; then use "ble".
#   ble   photos over Bluetooth only, no streaming.
# Needs: plumesign (https://github.com/claration/impactor/releases), usbmuxd running.
# First time: `plumesign account login -u you@example.com` (asks password + 2FA code).
set -euo pipefail

PLUMESIGN="${PLUMESIGN:-$HOME/Applications/impactor/plumesign-linux-x86_64}"
REPO="ismaelmehdid/BrightBlind"
VARIANT="${1:-wifi}"
TAG="${2:-ios-latest}"
WORK="$(mktemp -d)"

echo "→ downloading SecondVision-$VARIANT.ipa ($TAG) from $REPO"
gh release download "$TAG" -R "$REPO" -p "SecondVision-$VARIANT.ipa" -D "$WORK" --clobber

echo "→ signing with Apple ID and installing on the first connected iPhone"
export RUST_LOG="${RUST_LOG:-info}"
script -qec "$PLUMESIGN sign -p $WORK/SecondVision-$VARIANT.ipa --apple-id --register-and-install -o $WORK/SecondVision-$VARIANT-signed.ipa" /dev/null <<< $'\n\n\n' \
  | sed 's/\x1b\[[0-9;]*m//g; s/\x1b\[?25[lh]//g' | grep -E "INFO|WARN|ERROR|Error|Select" || true

test -f "$WORK/SecondVision-$VARIANT-signed.ipa" && echo "signed IPA: $WORK/SecondVision-$VARIANT-signed.ipa"
echo "done. A free Apple ID profile lasts 7 days; rerun to refresh."
