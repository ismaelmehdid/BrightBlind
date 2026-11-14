# Marv Labs developer digest (VexoHacks, 2026-11-14)

Sponsor tier per the event brief: gold ("From augmented technicians to autonomous maintenance"). Per the same brief,
Marv Labs cameras are available to hackers at the event.
Public confirmation: https://vexoai.com/hackathon lists "Marv Labs" among the sponsors (read live 2026-11-14). It gives no tier,
prize or hardware details. The Luma and YC event pages don't mention Marv Labs at all.

## Bottom line

**There is no public developer documentation, SDK, API reference, GitHub org, npm/PyPI package, or MCP server for Marv Labs.**
Searches of marvlabs.ai, GitHub, npm/PyPI and the open web (2026-11-14) turned up only marketing, about, careers, legal and calculator pages.
Similar names that are **not** Marv Labs: MARV Robotics (ternaris, ROS data platform, `marv`/`marv-cli` on PyPI), Marlabs, Marvis-Labs,
Marvel Labs (marvellabs.com).
Everything about getting video or frames off their camera at the event has to come from **Marv Labs staff on site**. Use the
checklist in section 5.

## 1. What is publicly known (official marvlabs.ai pages)

- Website: https://marvlabs.ai. Contact: contact@marvlabs.ai (the demo scheduler at /book "is not connected yet").
- Product: **SuperTechnician MPI(TM)**, "a lightweight camera headset that sees what technicians see". It recommends the repair,
  writes up the multi-point inspection (MPI), and sends the customer a narrated video. The homepage also calls the system **"Marv-L"**
  ("work that Marv-L documents on its own").
- Customer: franchise car dealer groups and their fixed-ops teams (service managers and directors, technicians). "It is not a consumer
  product. There is no app for a car owner to install." It is sold to the dealership.
- Value pitch: hands-free inspection video, with no stopping to film on a tablet. Their calculator cites +$230 per repair order when customers
  get photo/video (Cox Automotive 2025), applied to customer-pay work (55%, NADA 2025).
- Company mission (careers page): "Marv Labs is building autonomous maintenance for vehicles". The headset is a technician
  AI co-pilot that "next guides repairs and diagnoses problems". Every job "captures structured repair data", the
  "automotive-specific layer on top of increasingly capable general robotics models". Team is onsite in San Francisco.
- Roles they hire for hint at the internal stack (no public interface): a pipeline that "turns headset footage into inspections and
  customer videos" (ingestion, model integration, monitoring). Dealership management system (DMS) integration "through APIs and browser
  automation". Robotics teleoperation for service-bay tasks.
- Investor (third-party page): Transpose Platform portfolio, AI/ML sector.
- Third-party talk listing (Luma, "SFC: From Robot Intelligence to Real-World Deployment"): the Marv Labs co-founder and CTO spoke on
  extracting structured workflows from professional repair footage, and on verification and exception handling for robot deployment.

**Not public (unknown):** camera resolution/FPS/FOV, OS or firmware, connectivity (Wi-Fi / BLE / USB-C / UVC), on-device vs cloud
processing, video formats, any streaming protocol (RTSP/RTMP/WebRTC/WHIP), auth, rate limits, data retention, audio capture.

## 2. MCP server

**None found.** No official MCP server, URL, or package. There is no `claude mcp add` command to give.
If Marv Labs staff hand out an endpoint at the event, add it with the generic form (do not run until you have a real URL):

```bash
claude mcp add --transport http marvlabs <URL-from-Marv-staff>   # placeholder only, nothing official exists
```

## 3. Fit for this hackathon

- Marv's camera is a **first-person (egocentric) view** of hands at work. The Vexo band adds **wrist motion, taps and mic audio**.
  Together they cover the **Vision** track (camera), the **Voice** track (band mic) and **Ambient** (hands-free, no screen).
- Natural demo themes, aligned with Marv's mission (hands-free documentation, guided repair, structured repair data):
  - Tap the band to "bookmark" a moment. Grab the current camera frame, then have a vision model caption it and add it to an inspection log.
  - Wrist IMU segments the work ("loosening", "inspecting", "idle"). Camera frames at segment boundaries produce a narrated step-by-step report.
  - Spoken question via band mic ("what torque spec is this?"), plus the current frame, gives a spoken answer (TTS) with no screen.
  - Safety/ambient: detect a missing step (no frame of the tire tread before "done" tap) and nudge.
- Pair with Mastra (silver sponsor): one agent with image input + tools (`get-band-state`, `grab-frame`) + memory. See ../mastra.md.

## 4. Generic integration paths (NOT Marv-specific; use whichever the staff confirm)

These are standard ways to get frames from an unknown camera. None is documented by Marv Labs.

| If the headset... | Then on Windows 11 |
|---|---|
| shows up as a USB webcam (UVC) | Python OpenCV `cv2.VideoCapture(<index>)`, or browser `navigator.mediaDevices.getUserMedia` |
| exposes an RTSP/HTTP/MJPEG stream on Wi-Fi | OpenCV `cv2.VideoCapture("rtsp://...")`, or `ffmpeg -i <url> -vf fps=1 frame_%04d.jpg` |
| pairs with a phone app that records | ask for a file export (MP4) or a webhook/cloud API; sample frames with ffmpeg |
| only uploads to Marv's cloud | ask for API credentials and endpoint docs. Assume minutes of latency, not real time |

Python 3.12, untested sketch: grab a frame and POST it to a Mastra route (pip install opencv-python).

```python
import base64, json, urllib.request, cv2

SRC = 0  # webcam index, or "rtsp://<ip>:<port>/<path>" if Marv staff provide a stream URL (unknown)
cap = cv2.VideoCapture(SRC)
ok, frame = cap.read()
cap.release()
if not ok:
    raise SystemExit("no frame: check device index / URL")
ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
payload = {"type": "frame", "jpegBase64": base64.b64encode(jpg.tobytes()).decode()}
req = urllib.request.Request("http://localhost:4111/band/frame", data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
print(urllib.request.urlopen(req, timeout=60).read()[:500])
```

On the Mastra side, pass it as image content. The image-part shape is from Mastra's `generate()` docs, and the data-URL form is
an assumption that depends on the model provider:

```ts
await agent.generate([{ role: 'user', content: [
  { type: 'image', image: `data:image/jpeg;base64,${body.jpegBase64}`, mimeType: 'image/jpeg' },
  { type: 'text', text: 'Describe what the technician is inspecting. One sentence.' },
]}])
```

Windows gotchas (generic):
- Find the camera index: try 0, 1, 2. Use `cv2.VideoCapture(i, cv2.CAP_DSHOW)` if MSMF backend opens slowly or fails.
- Windows Settings > Privacy & security > Camera > "Let desktop apps access your camera" must be on for OpenCV.
- RTSP through OpenCV needs the FFmpeg backend (bundled in `opencv-python` wheels). Add `?tcp` or set
  `OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp` on lossy venue Wi-Fi.
- Venue Wi-Fi often isolates clients (AP isolation). A headset streaming over LAN may not be reachable from your laptop. Ask staff
  whether to use a hotspot.
- Faces and customer vehicles/plates may appear in footage. Ask Marv about any usage terms for demo footage.

## 5. Questions to ask Marv Labs staff at the event (to fill in the gaps)

1. How does the camera connect to a laptop: USB UVC, Wi-Fi stream (which protocol/URL), Bluetooth, or only through a phone app or cloud?
2. Is there a hackathon SDK, API, sample repo, or MCP server? Where are the docs? Do we need credentials or tokens?
3. Live frames vs recorded clips: latency, resolution, FPS, and do clips include audio?
4. Does the device run any on-device model, or expose events (e.g. "inspection step done")?
5. Any sample footage or datasets we may use? What are the usage/privacy terms?
6. How many devices, checkout process, battery life, charging?
7. Judging: is there a Marv Labs-specific prize and what are the criteria?

Record the answers back into this file. They are the only reliable source.

## 6. Links

- Website: https://marvlabs.ai
- About: https://marvlabs.ai/about
- Careers (Notion): https://marvlabs.ai/careers (-> https://marvlabs.notion.site/Careers-at-Marv-Labs-3cc0dd6b7c7d809aa568f826716d9707)
- Revenue calculator: https://marvlabs.ai/media/mpi-calculator.html
- Book a demo / contact: https://marvlabs.ai/book, contact@marvlabs.ai
- Privacy / Terms: https://marvlabs.ai/privacy, https://marvlabs.ai/terms (terms note: use of the Marv application is governed by the
  dealership agreement, so expect no public API terms)
- Hackathon sponsor list: https://vexoai.com/hackathon
- Third-party: Transpose Platform portfolio https://transposeplatform.vc/portfolio/marv-labs, talk listing https://luma.com/x7e6ylb6
