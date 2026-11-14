# ios/ — glasses relay (Andrii)

iPhone app that owns the Ray-Ban Meta session and does nothing else: forwards photos, sampled
stream frames and button presses to the backend over WebSocket, and plays whatever the
backend says into the glasses' speakers. All decisions live in `backend/`.

Scaffold (XcodeGen spec, CI workflow, DAT session boilerplate) is copied from Andrii's public
repo `andriidrok1/glasses-tutor`; product code (relay, modes, commands) written today.

## Build (no Mac in the team)

Every push to `main` that touches `ios/` runs `.github/workflows/ios-build.yml` on a macOS
runner and publishes two unsigned IPAs to the rolling release `ios-latest`:

- `SecondVision-wifi.ipa`: carries the Hotspot Configuration entitlement, needed for video
  streaming over the glasses' Wi-Fi.
- `SecondVision-ble.ipa`: no extra entitlements. Photos over Bluetooth only. Fallback if the
  signing account refuses the entitlement.

Install from Linux with a free Apple ID (profile lasts 7 days):

    ios/scripts/install.sh wifi      # or: ios/scripts/install.sh ble

## First run on the phone

1. Meta AI app: Developer Mode on for the glasses. iPhone: Settings → Privacy → Developer Mode on.
2. Open SecondVision, type the backend URL (`ws://host:port/ws`), it reconnects by itself.
3. "1. Register" (Meta AI opens, confirm), "2. Camera permission" (Allow always).
4. Session should reach `started`, stream `streaming` then `stopped`, shutter `started`,
   button `listening`. "Test voice" must come out of the glasses, not the phone.
5. "Capture" shows the photo at the bottom and sends it to the backend.
6. "Stream on": `frames seen` must climb. If it stays at 0 with the wifi build, Wi-Fi
   streaming is not working on this signing account; use photos only.

Phone needs mobile data: while joined to the glasses' Wi-Fi, iOS routes internet over
cellular. Keep the app on screen (Guided Access) so the session survives in the pocket.

## Messages (see root README for the full contract)

Up: `hello`, `photo` (`jpeg_b64`, `w`, `h`, `source: capture|stream`, `req_id`), `frame`
(`jpeg_b64`, `w`, `h`, `seq`), `state` (`glasses`, `mode`, `battery`), `button` (`press`).

Down: `capture` (`req_id`, `quality: small|medium|large|full`), `stream` (`on`, `fps`),
`say` (`text` and/or `audio_b64`, `interrupt`), `stop_speaking`, `beep`.

## Camera modes

`photo` (default): standalone shutter armed, stream stopped. A capture takes 2–5 s at
`medium`, 10+ s at `full`, all over Bluetooth.

`stream`: raw frames at 504x896, 7 fps from the glasses; the phone forwards `fps` JPEGs per
second (default 1). A capture in this mode is a still from the live stream, no mode switch.
Switching modes takes one to three seconds; the glasses heat up after ~30 minutes of
streaming, so the backend turns it on per scene, not all day.
