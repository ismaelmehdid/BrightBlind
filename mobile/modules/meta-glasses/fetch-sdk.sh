#!/usr/bin/env bash
# Fetches the Meta Wearables DAT SDK 1.0.1 xcframeworks into ios/Frameworks/ (git-ignored).
# Run before `expo prebuild` / `pod install`.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HERE/ios/Frameworks"
TAG="${MWDAT_TAG:-1.0.1}"
if [ -d "$DEST/MWDATCore.xcframework" ] && [ -d "$DEST/MWDATCamera.xcframework" ] && [ -d "$DEST/MWDATInputs.xcframework" ]; then
  echo "MWDAT xcframeworks already in $DEST"
  exit 0
fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone --quiet --depth 1 --branch "$TAG" https://github.com/facebook/meta-wearables-dat-ios.git "$TMP/dat" \
  || git clone --quiet --depth 1 --branch "$TAG" https://github.com/meta/meta-wearables-dat-ios.git "$TMP/dat"
mkdir -p "$DEST"
for f in MWDATCore MWDATCamera MWDATInputs; do
  rm -rf "$DEST/$f.xcframework"
  cp -R "$TMP/dat/$f.xcframework" "$DEST/"
done
echo "MWDAT $TAG xcframeworks copied to $DEST"
