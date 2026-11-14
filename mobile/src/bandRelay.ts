// The Vexo band over Bluetooth from the phone, relayed to Recall's /band WebSocket.
//
//   const band = useBand(recallUrl, token);
//   band.connect(); band.disconnect();
//   band.state, band.socket, band.battery, band.activity, band.steps, band.cadence, band.log
//
// To Recall (team contract, README "WebSocket contract"): hello {client: "band"}, then
// audio {seq, opus_b64}, event {kind}, activity {state, steps, cadence}, battery {percent}.
// The socket comes back every 2 s; audio is dropped while it is down.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Band } from './vexo/band.js';
import { BlePlxTransport, toBase64 } from './vexo/bleplx-transport.js';

/** The team's band number (on the bag). Kit rule: this band only, never another number. */
export const BAND_NUMBER = 63;

export type BandState = 'idle' | 'scanning' | 'connecting' | 'connected' | 'reconnecting' | 'error';
export type SocketState = 'off' | 'connecting' | 'up' | 'down';

export interface BandRelay {
  state: BandState;
  socket: SocketState;
  battery: number | null;
  activity: string | null;
  steps: number | null;
  cadence: number | null;
  error: string | null;
  log: string[];
  connect: () => void;
  disconnect: () => void;
}

const EVENT_KINDS = ['tap', 'double-tap', 'free-fall', 'tilt'] as const;
const LOG_MAX = 40;

/** "https://x.trycloudflare.com/ws?token=..." or "x:8100" -> "wss://x.trycloudflare.com/band?token=..." */
export function bandSocketUrl(recallUrl: string, token?: string | null): string {
  let u = recallUrl.trim();
  if (!/^[a-z]+:\/\//i.test(u)) u = (/^(localhost|127\.|10\.|192\.168\.)/.test(u) ? 'ws://' : 'wss://') + u;
  u = u.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
  const m = u.match(/^(wss?:\/\/[^/?#]+)/i);
  const base = m ? m[1] : u;
  let tok = token ?? '';
  if (!tok) {
    const q = recallUrl.match(/[?&]token=([^&#]+)/);
    if (q) tok = decodeURIComponent(q[1]);
  }
  // The team backend's /ws (contract v0) is kept as is; anything else is Recall, at /band.
  const path = /^wss?:\/\/[^/?#]+\/ws(?:[?#]|$)/i.test(u) ? '/ws' : '/band';
  return `${base}${path}${tok ? `?token=${encodeURIComponent(tok)}` : ''}`;
}

export function useBand(recallUrl: string | null | undefined, token?: string | null): BandRelay {
  const [state, setState] = useState<BandState>('idle');
  const [socket, setSocket] = useState<SocketState>('off');
  const [battery, setBattery] = useState<number | null>(null);
  const [activity, setActivity] = useState<string | null>(null);
  const [steps, setSteps] = useState<number | null>(null);
  const [cadence, setCadence] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);

  const wanted = useRef(false);               // true between connect() and disconnect()
  const bandRef = useRef<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const wsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seq = useRef(0);
  const last = useRef<{ battery?: object; activity?: object }>({});
  const runRef = useRef<() => Promise<void>>(async () => {});
  const urlRef = useRef<string | null>(null);
  urlRef.current = recallUrl ? bandSocketUrl(recallUrl, token) : null;

  const say = useCallback((line: string) => {
    const t = new Date().toTimeString().slice(0, 8);
    setLog((old) => [`${t} ${line}`, ...old].slice(0, LOG_MAX));
  }, []);

  const send = useCallback((msg: Record<string, unknown>) => {
    const ws = wsRef.current;
    // The team backend accepts only audio, event and activity from the band and drops the socket otherwise.
    if (msg.type === 'battery' && urlRef.current && /\/ws(\?|$)/.test(urlRef.current)) return false;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    try {
      ws.send(JSON.stringify({ ...msg, ts: Date.now() }));
      return true;
    } catch {
      return false;
    }
  }, []);

  // ---- socket to Recall: open while the band is wanted, back every 2 s -------------------
  const openSocket = useCallback(() => {
    if (wsTimer.current) { clearTimeout(wsTimer.current); wsTimer.current = null; }
    const url = urlRef.current;
    if (!wanted.current || !url) { setSocket('off'); return; }
    const old = wsRef.current;
    if (old && (old.readyState === WebSocket.OPEN || old.readyState === WebSocket.CONNECTING)) return;
    setSocket('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => {
      setSocket('up');
      say('Recall connected');
      ws.send(JSON.stringify({ type: 'hello', client: 'band', caps: ['audio', 'events', 'activity'], ts: Date.now() }));
      if (last.current.battery) send(last.current.battery as Record<string, unknown>);  // Recall only
      if (last.current.activity) send(last.current.activity as Record<string, unknown>);
    };
    ws.onmessage = (m) => {
      try {
        const msg = JSON.parse(String(m.data));
        if (msg.type === 'led') say(`Recall asked for LED ${msg.color} (ignored: the mic is on)`);
      } catch {}
    };
    ws.onerror = () => {};
    ws.onclose = () => {
      if (wsRef.current !== ws) return;
      wsRef.current = null;
      if (!wanted.current) { setSocket('off'); return; }
      setSocket('down');
      wsTimer.current = setTimeout(openSocket, 2000);
    };
  }, [say, send]);

  const closeSocket = useCallback(() => {
    if (wsTimer.current) { clearTimeout(wsTimer.current); wsTimer.current = null; }
    const ws = wsRef.current;
    wsRef.current = null;
    try { ws?.close(); } catch {}
    setSocket('off');
  }, []);

  // ---- the band -----------------------------------------------------------------------
  const setUp = useCallback(async (band: any) => {
    band.on('audio', (a: { opus: Uint8Array }) => {
      // Raw 20 ms Opus packet as the band sent it; dropped while the socket is down.
      if (wsRef.current?.readyState !== WebSocket.OPEN) return;
      seq.current = (seq.current + 1) % 0x7fffffff;
      send({ type: 'audio', seq: seq.current, opus_b64: toBase64(a.opus) });
    });
    for (const kind of EVENT_KINDS) {
      band.on(kind, () => {
        say(kind);
        send({ type: 'event', kind });
      });
    }
    band.on('activity', (e: { state: string; steps: number; cadence: number }) => {
      setActivity(e.state);
      setSteps(e.steps);
      setCadence(e.cadence);
      // The backend closes the socket on any other state (the kit can report 'unknown').
      if (e.state !== 'still' && e.state !== 'walk' && e.state !== 'run') return;
      const msg = { type: 'activity', state: e.state, steps: e.steps, cadence: e.cadence };
      last.current.activity = msg;
      send(msg);
    });
    band.on('battery', (e: { percent: number }) => {
      const msg = { type: 'battery', percent: e.percent };
      last.current.battery = msg;
      setBattery(e.percent);
      send(msg);
    });
    band.on('reconnecting', () => { setState('reconnecting'); say('Band link lost, reconnecting...'); });
    band.on('reconnected', () => { setState('connected'); say('Band back'); });
    band.on('disconnect', (e: { reason: string }) => {
      if (bandRef.current === band) bandRef.current = null;
      say(`Band disconnected (${e.reason})`);
      if (wanted.current) {
        setState('scanning');
        setTimeout(() => { if (wanted.current && !bandRef.current) void runRef.current(); }, 2000);
      } else {
        setState('idle');
      }
    });
    await band.configure({ events: true, activity: true, battery: true, audio: true });   // mic on: solid blue, LED locked
    try {
      const b = await band.getBattery();
      const msg = { type: 'battery', percent: b.percent };
      last.current.battery = msg;
      setBattery(b.percent);
      send(msg);
    } catch {}
  }, [say, send]);

  const run = useCallback(async (): Promise<void> => {
    while (wanted.current && !bandRef.current) {
      const transport = new BlePlxTransport(BAND_NUMBER);
      transport.onStatus = (s: string) => setState(s as BandState);
      setState('scanning');
      try {
        const band = await Band.connect(BAND_NUMBER, { transport, autoReconnect: true });
        if (!wanted.current) { await band.disconnect().catch(() => {}); break; }
        bandRef.current = band;
        say(`Connected to ${band.name}`);
        await setUp(band);
        setError(null);
        setState('connected');
        say('Mic, taps, steps and battery on');
        return;
      } catch (e: any) {
        if (!wanted.current) break;
        const why = e?.message ?? String(e);
        setError(why);
        say(why);
        if (e?.code === 'wrong-band') { setState('error'); wanted.current = false; closeSocket(); return; }
        setState('scanning');
        await new Promise((r) => setTimeout(r, 3000));     // keep looking until the band advertises (double-tap)
      }
    }
    if (!wanted.current) setState('idle');
  }, [say, setUp, closeSocket]);
  runRef.current = run;

  const connect = useCallback(() => {
    if (wanted.current) return;
    wanted.current = true;
    setError(null);
    openSocket();
    void run();
  }, [openSocket, run]);

  const disconnect = useCallback(() => {
    wanted.current = false;
    const band = bandRef.current;
    bandRef.current = null;
    band?.disconnect().catch(() => {});
    closeSocket();
    setState('idle');
  }, [closeSocket]);

  // A new Recall address: reopen the socket there.
  useEffect(() => {
    if (!wanted.current) return;
    const ws = wsRef.current;
    wsRef.current = null;
    try { ws?.close(); } catch {}
    openSocket();
  }, [recallUrl, token, openSocket]);

  // Unmount: let the band go (it resets itself when the link closes).
  useEffect(() => () => {
    wanted.current = false;
    bandRef.current?.disconnect().catch(() => {});
    bandRef.current = null;
    if (wsTimer.current) clearTimeout(wsTimer.current);
    try { wsRef.current?.close(); } catch {}
    wsRef.current = null;
  }, []);

  return { state, socket, battery, activity, steps, cadence, error, log, connect, disconnect };
}
