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

# The app's backend tokens never live in git or in the public release: they are written into the app's
# Info.plist (dict "BrightBlind") here, right before signing. $S/brightblind.env holds, one per line:
#   BAND_RELAY_TOKEN=...  GLASSES_RELAY_TOKEN=...  DASHBOARD_TOKEN=...  (optional BACKEND_URL=https://...)
# (the same values as the Railway backend's env; DASHBOARD_TOKEN = one entry of DASHBOARD_TOKENS)
CFG="${BRIGHTBLIND_ENV:-$S/brightblind.env}"
if [ -f "$CFG" ]; then
  (cd "$W" && rm -rf x && mkdir x && cd x && unzip -q ../BrightBlind-wifi.ipa)
  python3 - "$CFG" "$W"/x/Payload/*.app/Info.plist <<'PY'
import plistlib, sys
env = {}
for line in open(sys.argv[1]):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
keys = {"bandToken": "BAND_RELAY_TOKEN", "glassesToken": "GLASSES_RELAY_TOKEN",
        "dashboardToken": "DASHBOARD_TOKEN", "backendUrl": "BACKEND_URL"}
cfg = {k: env[e] for k, e in keys.items() if env.get(e)}
with open(sys.argv[2], "rb") as f:
    info = plistlib.load(f)
info["BrightBlind"] = cfg
with open(sys.argv[2], "wb") as f:
    plistlib.dump(info, f, fmt=plistlib.FMT_BINARY)
print("BrightBlind config written:", ", ".join(sorted(cfg)) or "nothing")
PY
  (cd "$W/x" && rm -f ../BrightBlind-wifi.ipa && zip -qr ../BrightBlind-wifi.ipa Payload)
else
  echo "warning: $CFG not found: the app will start without backend tokens (agents offline)"
fi

"$PLUMESIGN" sign -p "$W/BrightBlind-wifi.ipa" --pem "$S/dev-combined.pem" --provision "$S/SecondVision.mobileprovision" -o "$W/BrightBlind-wifi-team.ipa" 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "ERROR|Error" || true
test -f "$W/BrightBlind-wifi-team.ipa"
"$PMD" apps install "$W/BrightBlind-wifi-team.ipa" 2>&1 | tail -1
echo "installed $W/BrightBlind-wifi-team.ipa (bundle com.andriidrok.secondvision, team SDAGV82ZXL)"
