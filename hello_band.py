# Connect to our Vexo band, show its battery, cycle the light, then disconnect.
#   python hello_band.py          our band over Bluetooth (double-tap it first)
#   python hello_band.py --usb    our band on the USB cable (add --port COM5 on Windows)
#   python hello_band.py --sim    a pretend band, no hardware
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vexo-open-kit", "python"))
from vexo_open.sync import Band  # noqa: E402

BAND = 63  # our team's band number: Vexo-HACK-63. Change it only here.

transport = "sim" if "--sim" in sys.argv else "serial" if "--usb" in sys.argv else "ble"
options = {}
if "--port" in sys.argv:  # Windows does not name the band's port, so give it: --port COM5
    options["port"] = sys.argv[sys.argv.index("--port") + 1]
band = Band.connect(BAND, transport, **options)  # fails with "wrong-band" if another band answers
print("Connected to", band.name)

for colour in ["#ff0000", "#00ff00", "#0000ff"]:
    print("LED", colour)
    band.set_led(colour)
    time.sleep(1)

band.set_led("#ffffff", pattern="blink", period=500)
band.wait(3)
band.disconnect()
print("Done")
