#!/usr/bin/env bash
# Sign the wifi IPA with the paid-team development certificate + profile (Hotspot Configuration
# entitlement survives, unlike with a free Apple ID) and install it over USB.
# Needs: ~/.config/appstore/secondvision/{dev-combined.pem,SecondVision.mobileprovision} (made 2026-11-14
# via the App Store Connect API: cert 35TZPUX88D, profile M8A23S2564, device 4D564C4MC5), plumesign, pymobiledevice3.
set -euo pipefail
S="$HOME/.config/appstore/secondvision"
PLUMESIGN="${PLUMESIGN:-$HOME/Applications/impactor/plumesign-linux-x86_64}"
PMD="${PMD:-$HOME/.local/bin/pymobiledevice3}"
TAG="${1:-ios-latest}"
W="$(mktemp -d)"
gh release download "$TAG" -R ismaelmehdid/BrightBlind -p "SecondVision-wifi.ipa" -D "$W" --clobber
"$PLUMESIGN" sign -p "$W/SecondVision-wifi.ipa" --pem "$S/dev-combined.pem" --provision "$S/SecondVision.mobileprovision" -o "$W/SecondVision-wifi-team.ipa" 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "ERROR|Error" || true
test -f "$W/SecondVision-wifi-team.ipa"
"$PMD" apps install "$W/SecondVision-wifi-team.ipa" 2>&1 | tail -1
echo "installed $W/SecondVision-wifi-team.ipa (bundle com.andriidrok.secondvision, team SDAGV82ZXL)"
