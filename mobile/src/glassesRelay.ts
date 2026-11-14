// Glasses <-> Recall relay: the JS twin of ios/Sources/AppModel.swift + Relay.swift.
// A dumb pipe: native glasses events go up as contract messages (photo, frame, state, button),
// Recall's commands come down and run on the glasses (capture, stream/burst, say, stop_speaking).
import { useEffect, useRef, useState } from 'react';
import { Linking } from 'react-native';
import * as Glasses from '../modules/meta-glasses';
import type { GlassesState, GlassesPhoto } from '../modules/meta-glasses';

export type RelayLink = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';
type Listener = () => void;

const RECONNECT_MS = 2000;
const MAX_LOG = 200;

/** `https://x.trycloudflare.com` + token -> `wss://x.trycloudflare.com/glasses?token=...`. A full ws(s) URL is kept. */
export function glassesWsUrl(base: string, token: string): string {
  let u = base.trim().replace(/\/+$/, '').replace(/^http/, 'ws');
  if (!/\/glasses(\?|$)/.test(u)) u += '/glasses';
  if (token && !/[?&]token=/.test(u)) u += (u.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);
  return u;
}

export class GlassesRelay {
  link: RelayLink = 'disconnected';
  state: GlassesState | null = null;
  lastPhoto: GlassesPhoto | null = null;
  log: string[] = [];
  sent = 0;
  received = 0;

  private url = '';
  private ws: WebSocket | null = null;
  private wanted = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private subs: { remove(): void }[] = [];
  private listeners = new Set<Listener>();

  constructor() {
    this.subs.push(
      Glasses.addListener('onLog', ({ line }) => this.addLog(line, false)),
      Glasses.addListener('onState', (s) => {
        this.state = s;
        const m: Record<string, unknown> = { type: 'state', glasses: s.glasses, mode: s.mode };
        if (s.battery != null) m.battery = s.battery;
        this.send(m);
        this.emit();
      }),
      Glasses.addListener('onPhoto', (p) => {
        this.lastPhoto = p;
        const m: Record<string, unknown> = { type: 'photo', jpeg_b64: p.jpeg_b64, w: p.w, h: p.h, source: p.source };
        if (p.req_id) m.req_id = p.req_id;
        this.send(m);
        this.emit();
      }),
      Glasses.addListener('onFrame', (f) => {
        this.send({ type: 'frame', jpeg_b64: f.jpeg_b64, w: f.w, h: f.h, seq: f.seq });
      }),
      Glasses.addListener('onButton', ({ press }) => this.send({ type: 'button', press })),
    );
    // Meta AI calls back with secondvision://...?metaWearablesAction=... after registration / permission.
    this.subs.push(Linking.addEventListener('url', ({ url }) => { Glasses.handleUrl(url); }));
    Linking.getInitialURL().then((url) => { if (url) Glasses.handleUrl(url); }).catch(() => {});
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => { this.listeners.delete(fn); };
  }

  private emit() {
    for (const fn of this.listeners) fn();
  }

  addLog(line: string, stamp = true) {
    const t = stamp ? new Date().toTimeString().slice(0, 8) + ' ' : '';
    this.log = [...this.log, t + line].slice(-MAX_LOG);
    this.emit();
  }

  /** Start the glasses side (configure + watch devices) and the Recall link. */
  async start(url: string) {
    if (!Glasses.isAvailable) this.addLog('glasses module not in this build (Expo Go / Android): relay only');
    else await Glasses.configure();
    this.setUrl(url);
  }

  setUrl(url: string) {
    if (url === this.url && this.wanted) return;
    this.url = url;
    this.close();
    if (!url) return;
    this.wanted = true;
    this.open();
  }

  stop() {
    this.wanted = false;
    this.close();
  }

  destroy() {
    this.stop();
    for (const s of this.subs) s.remove();
    this.subs = [];
    this.listeners.clear();
  }

  private close() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null;
      try { ws.close(); } catch {}
    }
    this.setLink('disconnected');
  }

  private setLink(l: RelayLink) {
    if (this.link !== l) { this.link = l; this.emit(); }
  }

  private open() {
    if (!this.wanted || this.ws) return;
    this.setLink(this.link === 'disconnected' ? 'connecting' : 'reconnecting');
    this.addLog('ws connecting to ' + this.url.replace(/token=[^&]+/, 'token=…'));
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.url);
    } catch (e) {
      this.addLog('ws: bad url ' + String(e));
      this.retry();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      if (this.ws !== ws) return;
      this.setLink('connected');
      this.send({ type: 'hello', client: 'glasses', caps: ['capture', 'stream', 'say', 'button'] });
      // A restarted backend knows nothing about the glasses: repeat the current state after every hello.
      Glasses.getState().then((s) => {
        if (!s) return;
        this.state = s;
        const m: Record<string, unknown> = { type: 'state', glasses: s.glasses, mode: s.mode };
        if (s.battery != null) m.battery = s.battery;
        this.send(m);
      }).catch(() => {});
    };
    ws.onmessage = (ev) => {
      if (this.ws !== ws) return;
      this.received += 1;
      let cmd: any;
      try { cmd = JSON.parse(typeof ev.data === 'string' ? ev.data : String(ev.data)); } catch {
        this.addLog('ws: not JSON');
        return;
      }
      if (cmd && typeof cmd === 'object') this.handle(cmd);
    };
    ws.onerror = () => {};
    ws.onclose = (ev) => {
      if (this.ws !== ws) return;
      this.addLog(`ws dropped (${ev.code}${ev.reason ? ' ' + ev.reason : ''})`);
      this.ws = null;
      this.retry();
    };
  }

  private retry() {
    if (!this.wanted) return;
    this.setLink('reconnecting');
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.timer = null; this.open(); }, RECONNECT_MS);
  }

  /** Adds `ts` and sends. Silently drops when not connected (Recall re-asks). */
  send(message: Record<string, unknown>) {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(JSON.stringify({ ...message, ts: Date.now() }));
      this.sent += 1;
    } catch (e) {
      this.addLog('ws send: ' + String(e));
    }
  }

  private handle(cmd: any) {
    switch (cmd.type) {
      case 'capture':
        Glasses.capture(typeof cmd.req_id === 'string' ? cmd.req_id : null, typeof cmd.quality === 'string' ? cmd.quality : 'medium');
        break;
      case 'stream':
      case 'burst': {
        // burst = stream for now: the sampled stream frames come back as `frame` messages.
        const on = cmd.on === true || cmd.on === 1;
        Glasses.setStreaming(on, typeof cmd.fps === 'number' ? cmd.fps : undefined);
        break;
      }
      case 'say':
        if (typeof cmd.audio_b64 === 'string' && cmd.audio_b64) Glasses.playMp3(cmd.audio_b64);
        else if (typeof cmd.text === 'string' && cmd.text) Glasses.say(cmd.text);
        break;
      case 'stop_speaking':
        Glasses.stopSpeaking();
        break;
      case 'beep':
        Glasses.beep();
        break;
      case 'hello':
      case 'ack':
      case 'pong':
        break;
      default:
        this.addLog('unknown command: ' + cmd.type);
    }
  }
}

let shared: GlassesRelay | null = null;
/** One relay per app: the native module is a singleton too. */
export function getGlassesRelay(): GlassesRelay {
  if (!shared) shared = new GlassesRelay();
  return shared;
}

/**
 * For the main screen. `recallUrl` is Recall's base address (https://… or wss://…/glasses?token=…);
 * empty means no link. Re-renders on relay link, glasses state, photos and log lines (not on frames).
 */
export function useGlasses(recallUrl: string, token: string) {
  const relay = useRef(getGlassesRelay()).current;
  const [, setTick] = useState(0);

  useEffect(() => relay.subscribe(() => setTick((n) => n + 1)), [relay]);

  useEffect(() => {
    const url = recallUrl.trim() ? glassesWsUrl(recallUrl, token) : '';
    relay.start(url);
  }, [relay, recallUrl, token]);

  return {
    available: Glasses.isAvailable,
    link: relay.link,
    state: relay.state,
    glasses: relay.state?.glasses ?? 'disconnected',
    lastPhoto: relay.lastPhoto,
    log: relay.log,
    register: () => Glasses.register(),
    requestCameraPermission: () => Glasses.requestCameraPermission(),
    connect: () => Glasses.connect(),
    reconnect: () => Glasses.reconnect(),
    capture: (reqId: string | null = `app-${Date.now()}`, quality = 'medium') => Glasses.capture(reqId, quality),
    setStreaming: (on: boolean, fps?: number) => Glasses.setStreaming(on, fps),
    say: (text: string) => Glasses.say(text),
    stopSpeaking: () => Glasses.stopSpeaking(),
  };
}
