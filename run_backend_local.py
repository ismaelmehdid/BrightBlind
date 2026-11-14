"""Run the team backend (backend/server.py) on this laptop, with the keys from the root .env.

    backend\\.venv\\Scripts\\python.exe run_backend_local.py

Local defaults: http://127.0.0.1:8765 (dashboard), ws://127.0.0.1:8765/ws (relays), LIVE_ONLY=0 so a
missing device does not block a test, REQUIRE_WAKE_WORD=1 so the planner only reacts to "Second Vision ..."
or after a double-tap (the band hears everything; Recall's memory keeps it all anyway).
Keys stay in .env (DEEPGRAM_API_KEY, GEMINI_API_KEY, optional GOOGLE_MAPS_API_KEY), never on a command line.
If BAND_RELAY_TOKEN / GLASSES_RELAY_TOKEN / DASHBOARD_TOKENS are set in .env, every connection must carry them:
set them before exposing this port through a tunnel.
"""
import os
import runpy
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
for key, value in {"HOST": "127.0.0.1", "PORT": "8765", "LIVE_ONLY": "0", "REQUIRE_WAKE_WORD": "1",
                   "VOICE_TTS_PROVIDER": "deepgram", "BACKEND_DATA_DIR": str(ROOT / "backend" / ".data")}.items():
    os.environ.setdefault(key, value)
os.environ.pop("RECALL_WS_URL", None)       # the memory runs inside the backend now (backend/memory.py)
os.chdir(ROOT / "backend")
sys.path.insert(0, str(ROOT / "backend"))
sys.argv = ["server.py"]
print(f"Team backend on http://127.0.0.1:{os.environ['PORT']}  (relays: ws://127.0.0.1:{os.environ['PORT']}/ws)")
runpy.run_path("server.py", run_name="__main__")
