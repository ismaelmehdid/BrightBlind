// Bluetooth on the phone (iOS and Android dev builds) through react-native-ble-plx.
// Same shape as the kit's transports/web-bluetooth.js: open, reopen, close, send, onFrame, onClose.
// Scans only for the band with the exact name built from the band number, together with the kit's
// service UUID (kit rule: never connect to the first Vexo band found). Band.connect then checks the
// number the band reports.
import { BleManager } from 'react-native-ble-plx';
import { Transport, VexoError, ELSEWHERE_HELP } from './transport.js';
import { SERVICE_UUID, RX_UUID, TX_UUID, MAX_FRAME, bandName } from './codec.js';

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const B64_INDEX = (() => { const t = new Int16Array(128).fill(-1); for (let i = 0; i < 64; i++) t[B64.charCodeAt(i)] = i; return t; })();

/** Bytes -> base64 (what ble-plx writes). */
export function toBase64(bytes) {
  let out = '';
  let i = 0;
  for (; i + 2 < bytes.length; i += 3) {
    const n = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
    out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + B64[(n >> 6) & 63] + B64[n & 63];
  }
  if (i < bytes.length) {
    const n = (bytes[i] << 16) | ((i + 1 < bytes.length ? bytes[i + 1] : 0) << 8);
    out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + (i + 1 < bytes.length ? B64[(n >> 6) & 63] : '=') + '=';
  }
  return out;
}

/** base64 -> bytes (what ble-plx hands us). */
export function fromBase64(text) {
  const clean = text.replace(/[^A-Za-z0-9+/]/g, '');
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let o = 0, bits = 0, acc = 0;
  for (let i = 0; i < clean.length; i++) {
    acc = (acc << 6) | B64_INDEX[clean.charCodeAt(i)];
    bits += 6;
    if (bits >= 8) { bits -= 8; out[o++] = (acc >> bits) & 0xff; }
  }
  return o === out.length ? out : out.subarray(0, o);
}

let sharedManager = null;
/** One BleManager for the whole app (ble-plx wants a single instance). */
export function bleManager() {
  if (!sharedManager) sharedManager = new BleManager();
  return sharedManager;
}

function within(promise, seconds, makeError) {
  let timer;
  const late = new Promise((_ok, fail) => { timer = setTimeout(() => fail(makeError()), seconds * 1000); });
  return Promise.race([promise, late]).finally(() => clearTimeout(timer));
}

export class BlePlxTransport extends Transport {
  kind = 'ble';
  /** Seconds to look for the band in one open(). The band is findable 60 s after a double-tap. */
  scanSeconds = 30;
  /** Seconds for the found band to answer. */
  connectSeconds = 20;
  /** Optional: told 'scanning' and 'connecting' as open() goes on. */
  onStatus = (_status) => {};

  /** @param {number} number the team's band number (63 = Vexo-HACK-63) */
  constructor(number, manager = bleManager()) {
    super();
    this.bandName = bandName(number);
    this.manager = manager;
    this.device = null;
    this._writes = Promise.resolve();
    this._closing = false;
    this._up = false;
    this._subs = [];
  }

  async _poweredOn() {
    const state = await this.manager.state();
    if (state === 'PoweredOn') return;
    if (state === 'Unauthorized') throw new VexoError('no-bluetooth', 'Bluetooth permission is off for this app: allow it in Settings.');
    await within(new Promise((ok) => {
      const sub = this.manager.onStateChange((s) => { if (s === 'PoweredOn') { sub.remove(); ok(); } }, true);
    }), 10, () => new VexoError('no-bluetooth', `Bluetooth is ${state}. Switch it on and try again.`));
  }

  _scan() {
    return new Promise((ok, fail) => {
      let done = false;
      const finish = (err, device) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        this.manager.stopDeviceScan().catch?.(() => {});
        if (err) fail(err); else ok(device);
      };
      const timer = setTimeout(() => finish(new VexoError('not-found-nearby', `Could not see ${this.bandName}. ${ELSEWHERE_HELP} `
        + `Then double-tap ${this.bandName} (it blinks blue for a minute), keep it close, and try again.`)), this.scanSeconds * 1000);
      // Filter on the service UUID (in the band's first advert packet) and then on the exact name.
      this.manager.startDeviceScan([SERVICE_UUID], { allowDuplicates: false }, (error, device) => {
        if (error) return finish(new VexoError('no-bluetooth', `Bluetooth scan failed: ${error.message}`));
        if (!device) return;
        if (device.localName === this.bandName || device.name === this.bandName) finish(null, device);
      });
    });
  }

  async open() {
    await this._poweredOn();
    this.onStatus('scanning');
    this.device = await this._scan();
    this.onStatus('connecting');
    await this._connect();
  }

  /** Connect again to the band found before (auto-reconnect); falls back to a scan. */
  async reopen() {
    if (!this.device) return this.open();
    try {
      await this._connect();
    } catch {
      this.device = await this._scan();
      await this._connect();
    }
  }

  _dropSubs() {
    for (const s of this._subs) { try { s.remove(); } catch {} }
    this._subs = [];
  }

  async _connect() {
    const id = this.device.id;
    this._closing = false;
    this._writes = Promise.resolve();
    this._dropSubs();
    try {
      await within((async () => {
        const dev = await this.manager.connectToDevice(id, { requestMTU: 247 });
        await dev.discoverAllServicesAndCharacteristics();
        // Listen before the first command, or its answer could be missed.
        this._subs.push(this.manager.monitorCharacteristicForDevice(id, SERVICE_UUID, TX_UUID, (error, ch) => {
          if (error || !ch?.value) return;          // errors here come with the disconnect, handled below
          this.onFrame(fromBase64(ch.value));
        }));
        this._subs.push(this.manager.onDeviceDisconnected(id, () => {
          const wasUp = this._up;
          this._up = false;
          this._dropSubs();
          if (wasUp) this.onClose(this._closing ? 'closed' : 'lost');
        }));
        // Give the notify subscription a moment to be enabled on the band before commands go out.
        await new Promise((r) => setTimeout(r, 300));
      })(), this.connectSeconds, () => new Error(`the band did not answer within ${this.connectSeconds} seconds.`));
      this._up = true;
    } catch (e) {
      this._up = false;
      this._dropSubs();
      this.manager.cancelDeviceConnection(id).catch(() => {});
      throw new VexoError('not-found-nearby', `Could not connect to ${this.bandName}: ${e.message} `
        + 'Double-tap the band to wake it, keep it close, and try again.');
    }
  }

  async close() {
    this._closing = true;
    this.manager.stopDeviceScan()?.catch?.(() => {});
    if (this.device) await this.manager.cancelDeviceConnection(this.device.id).catch(() => {});
  }

  send(frame) {
    const write = this._writes.then(() => {
      if (!this._up || !this.device) throw new VexoError('not-connected', 'Not connected to a band.');
      if (frame.length > MAX_FRAME) throw new VexoError('bad-arg', `A frame can be at most ${MAX_FRAME} bytes.`);
      return this.manager.writeCharacteristicWithResponseForDevice(this.device.id, SERVICE_UUID, RX_UUID, toBase64(frame));
    });
    this._writes = write.catch(() => {});
    return write;
  }
}
