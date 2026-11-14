#!/usr/bin/env bash
# Sign the Expo app's IPA (release mobile-latest, built by .github/workflows/mobile-ios.yml) with the
# paid-team development certificate + profile and install it over USB. Same cert/profile as
# ios/scripts/install-team.sh: the app keeps bundle id com.andriidrok.secondvision on purpose.
# Needs: ~/.config/appstore/secondvision/{dev-combined.pem,SecondVision.mobileprovision}, plumesign, pymobiledevice3.
set -euo pipefail
S="$HOME/.config/appstore/secondvision"
PLUMESIGN="${PLUMESIGN:-$HOME/Applications/impactor/plumesign-linux-x86_64}"
PMD="${PMD:-$HOME/.local/bin/pymobiledevice3}"
TAG="${1:-mobile-latest}"
W="$(mktemp -d)"
gh release download "$TAG" -R ismaelmehdid/BrightBlind -p "BrightBlind-wifi.ipa" -D "$W" --clobber
"$PLUMESIGN" sign -p "$W/BrightBlind-wifi.ipa" --pem "$S/dev-combined.pem" --provision "$S/SecondVision.mobileprovision" -o "$W/BrightBlind-wifi-team.ipa" 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "ERROR|Error" || true
test -f "$W/BrightBlind-wifi-team.ipa"
"$PMD" apps install "$W/BrightBlind-wifi-team.ipa" 2>&1 | tail -1
echo "installed $W/BrightBlind-wifi-team.ipa (bundle com.andriidrok.secondvision, team SDAGV82ZXL)"
