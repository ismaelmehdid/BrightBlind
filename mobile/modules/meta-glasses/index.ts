// Ray-Ban Meta glasses (Meta Wearables DAT 1.0.1), iOS only. Native side: ios/MetaGlassesModule.swift.
import { NativeModule, requireOptionalNativeModule } from 'expo';
import { Platform } from 'react-native';
import type { EventSubscription } from 'expo';

export type GlassesLink = 'disconnected' | 'connected' | 'streaming';

export type GlassesState = {
  glasses: GlassesLink;
  session: string;        // SDK session state, e.g. "started", "stopped"
  stream: string;         // SDK stream state, e.g. "streaming", "stopped"
  photo: string;          // standalone shutter state
  mode: 'photo' | 'stream';
  registration: string;   // registration with Meta AI
  device: string;         // human readable device line
  buttonReady: boolean;
  battery?: number | null;
};

export type GlassesPhoto = {
  jpeg_b64: string;
  w: number;
  h: number;
  source: 'capture' | 'stream';
  req_id?: string | null;
};

export type GlassesFrame = { jpeg_b64: string; w: number; h: number; seq: number };
export type GlassesButton = { press: 'short' | 'double' | 'hold' };
export type GlassesLog = { line: string };

export type MetaGlassesEvents = {
  onState: (e: GlassesState) => void;
  onPhoto: (e: GlassesPhoto) => void;
  onFrame: (e: GlassesFrame) => void;
  onButton: (e: GlassesButton) => void;
  onLog: (e: GlassesLog) => void;
};

declare class MetaGlassesNative extends NativeModule<MetaGlassesEvents> {
  configure(): Promise<boolean>;
  register(): Promise<void>;
  requestCameraPermission(): Promise<void>;
  handleUrl(url: string): Promise<boolean>;
  connect(): Promise<void>;
  reconnect(): Promise<void>;
  capture(reqId: string | null, quality: string): Promise<void>;
  setStreaming(on: boolean, fps: number | null): Promise<void>;
  say(text: string): Promise<void>;
  playMp3(base64: string): Promise<void>;
  stopSpeaking(): Promise<void>;
  beep(): Promise<void>;
  getState(): Promise<GlassesState>;
}

// Optional: Expo Go / Android / web have no such module, and the app must still run there.
const native: MetaGlassesNative | null =
  Platform.OS === 'ios' ? requireOptionalNativeModule<MetaGlassesNative>('MetaGlasses') : null;

/** True in a dev/release build that contains the native module. */
export const isAvailable = native != null;

const noop = async () => {};

export const configure = (): Promise<boolean> => (native ? native.configure() : Promise.resolve(false));
export const register = (): Promise<void> => (native ? native.register() : noop());
export const requestCameraPermission = (): Promise<void> => (native ? native.requestCameraPermission() : noop());
export const handleUrl = (url: string): Promise<boolean> => (native ? native.handleUrl(url) : Promise.resolve(false));
export const connect = (): Promise<void> => (native ? native.connect() : noop());
export const reconnect = (): Promise<void> => (native ? native.reconnect() : noop());
export const capture = (reqId: string | null = null, quality: string = 'medium'): Promise<void> =>
  native ? native.capture(reqId, quality) : noop();
export const setStreaming = (on: boolean, fps?: number): Promise<void> =>
  native ? native.setStreaming(on, typeof fps === 'number' ? fps : null) : noop();
export const say = (text: string): Promise<void> => (native ? native.say(text) : noop());
export const playMp3 = (base64: string): Promise<void> => (native ? native.playMp3(base64) : noop());
export const stopSpeaking = (): Promise<void> => (native ? native.stopSpeaking() : noop());
export const beep = (): Promise<void> => (native ? native.beep() : noop());
export const getState = (): Promise<GlassesState | null> => (native ? native.getState() : Promise.resolve(null));

export function addListener<K extends keyof MetaGlassesEvents>(
  event: K,
  listener: MetaGlassesEvents[K],
): EventSubscription {
  if (!native) return { remove() {} };
  return native.addListener(event, listener);
}
