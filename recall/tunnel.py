"""A public https address for this laptop's Recall, so the glasses' phone (on mobile data) can reach it.

Uses a Cloudflare quick tunnel (`cloudflared tunnel --url ...`): no account, a new random
https://<words>.trycloudflare.com address on every start. Recall then requires its token on every path.
"""
import asyncio
import os
import re
import shutil
from pathlib import Path

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_cloudflared():
    found = shutil.which("cloudflared")
    if found:
        return found
    for p in (Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe",
              Path(os.getenv("ProgramFiles(x86)", "")) / "cloudflared" / "cloudflared.exe",
              Path(os.getenv("ProgramFiles", "")) / "cloudflared" / "cloudflared.exe"):
        if p.is_file():
            return str(p)
    return None


async def start_tunnel(port, timeout=40):
    """Start the tunnel; returns (process, public https URL). Raises RuntimeError with what to do."""
    exe = find_cloudflared()
    if not exe:
        raise RuntimeError("cloudflared is not installed. Install it with:  winget install --id Cloudflare.cloudflared")
    proc = await asyncio.create_subprocess_exec(
        exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)

    async def find_url():
        while True:
            line = await proc.stderr.readline()
            if not line:
                raise RuntimeError("cloudflared stopped before it gave an address")
            m = URL_RE.search(line.decode(errors="replace"))
            if m:
                return m.group(0)

    try:
        url = await asyncio.wait_for(find_url(), timeout)
    except Exception:
        proc.kill()
        raise
    asyncio.create_task(_drain(proc))       # keep reading, or cloudflared blocks on a full pipe
    return proc, url


async def _drain(proc):
    while await proc.stderr.readline():
        pass
