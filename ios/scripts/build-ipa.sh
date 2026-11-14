#!/usr/bin/env bash
# Usage: scripts/build-ipa.sh <variant> [XCODEBUILD_SETTING=value ...]
# Builds an unsigned Release .app and zips it into SecondVision-<variant>.ipa
set -euo pipefail
VARIANT="$1"; shift
DD="build-$VARIANT"
xcodebuild build \
  -project SecondVision.xcodeproj \
  -scheme SecondVision \
  -configuration Release \
  -sdk iphoneos \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$DD" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGN_IDENTITY="" \
  DEVELOPMENT_TEAM="" \
  "$@" \
  | tee "build-$VARIANT.log" | grep -E "error:|BUILD" || true
grep -q "BUILD SUCCEEDED" "build-$VARIANT.log"
APP=$(find "$DD/Build/Products/Release-iphoneos" -maxdepth 1 -name "*.app" | head -1)
test -n "$APP"
rm -rf "Payload-$VARIANT" && mkdir -p "Payload-$VARIANT/Payload" && cp -R "$APP" "Payload-$VARIANT/Payload/"
( cd "Payload-$VARIANT" && zip -qr "../SecondVision-$VARIANT.ipa" Payload )
ls -la "SecondVision-$VARIANT.ipa"
