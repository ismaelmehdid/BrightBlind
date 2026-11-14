# Record our Vexo band's microphone to recording.wav and print how loud it was.
# The sound stays on this laptop: nothing is sent anywhere.
#   python record_band.py --usb --port COM5           5 seconds from our band on the USB cable
#   python record_band.py --usb --port COM5 --seconds 10
#   python record_band.py --sim                        a pretend band playing the kit's sample voice
import os
import sys

KIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vexo-open-kit")
sys.path.insert(0, os.path.join(KIT, "python"))
from vexo_open import audio  # noqa: E402
from vexo_open.sync import Band  # noqa: E402

BAND = 63  # our team's band number: Vexo-HACK-63. Change it only here.
OUT = "recording.wav"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


seconds = float(arg("--seconds", 5))
transport = "sim" if "--sim" in sys.argv else "serial" if "--usb" in sys.argv else "ble"
options = {}
if arg("--port"):  # Windows does not name the band's port, so give it: --port COM5
    options["port"] = arg("--port")
if transport == "sim":  # a pretend band is silent unless it gets a recording to play
    options["audio_packets"] = audio.ogg_packets(os.path.join(KIT, "dashboard", "speech", "sample-speech.opus"))

packets = []
band = Band.connect(BAND, transport, **options)  # fails with "wrong-band" if another band answers
print("Connected to", band.name)
band.on("audio", packets.append)
band.configure(audio=True)  # the band's light goes solid blue while the microphone is on
print("Recording %g seconds: speak near the band..." % seconds)
band.wait(seconds)
band.configure(audio=False)
band.disconnect()

if not packets:
    sys.exit("No sound arrived from the band.")
print("Got %d packets (%.1f seconds). Decoding..." % (len(packets), len(packets) / 50))
pcm = audio.decode_packets(packets)
audio.write_wav(OUT, pcm)
print("Saved %s, loudness %.0f dB (about -50 quiet room, -30 speech nearby)" % (OUT, audio.level_db(pcm)))
