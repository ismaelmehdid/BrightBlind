// BrightBlind: the band, the Meta glasses and every agent on one phone screen.
// Talks to Recall (laptop, /ws: band, glasses, Watcher, Guide, Memory) and, when set, reads the team
// backend's /api/state (Planner, Vision, Transit). In the iOS build this phone is also the glasses relay
// (modules/meta-glasses, Meta DAT SDK) and the band's Bluetooth link; in Expo Go those cards only show status.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Image, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { useBand } from './src/bandRelay';
import { useGlasses } from './src/glassesRelay';
import { bundleConfig } from './modules/meta-glasses';

type Ctx = Record<string, any>;
type Step = { ts: number; agent: string; state: string; detail: string; from: 'recall' | 'backend' };
type Photo = { id: number | string; ts: number; source: string; caption: string; jpeg_b64: string };
type Line = { id: number; ts: number; text: string; source: string };
type Settings = { recallUrl: string; recallToken: string; backendUrl: string; backendToken: string; glassesUrl: string; bandUrl: string };

// One fixed backend (the team's Railway coordinator). Tokens come from the signed build's Info.plist
// (mobile/scripts/install-team.sh writes them right before signing), or from .env.local in development.
const RAILWAY = 'https://backend-production-902365d4.up.railway.app';
const CFG = bundleConfig();
const BACKEND = (CFG.backendUrl || process.env.EXPO_PUBLIC_BACKEND_URL || RAILWAY).replace(/\/+$/, '');
const relayUrl = (token?: string) => (token ? BACKEND.replace(/^http/, 'ws') + '/ws?token=' + encodeURIComponent(token) : '');
const DEFAULTS: Settings = {
  recallUrl: process.env.EXPO_PUBLIC_RECALL_URL ?? '',
  recallToken: process.env.EXPO_PUBLIC_RECALL_TOKEN ?? '',
  backendUrl: BACKEND,
  backendToken: CFG.dashboardToken || process.env.EXPO_PUBLIC_BACKEND_TOKEN || '',
  glassesUrl: relayUrl(CFG.glassesToken) || process.env.EXPO_PUBLIC_GLASSES_URL || '',
  bandUrl: relayUrl(CFG.bandToken) || process.env.EXPO_PUBLIC_BAND_URL || '',
};
const KEY = 'brightblind.settings.v2';   // v1 saves held empty fields that hid the built-in values

const C = {
  bg: '#0b0f14', card: '#141b23', line: '#222c37', text: '#e8eef4', dim: '#8a98a8',
  ok: '#2ecc71', warn: '#f5b041', bad: '#e74c3c', accent: '#4aa3ff', burst: '#1abc9c',
};
const AGENT_COLOR: Record<string, string> = {
  Watcher: '#4aa3ff', Guide: '#1abc9c', Burst: '#1abc9c', Memory: '#b07cff', Vision: '#f5b041',
};

const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const wsUrl = (base: string, token: string) =>
  base.trim().replace(/\/+$/, '').replace(/^http/, 'ws') + '/ws' + (token ? `?token=${encodeURIComponent(token)}` : '');

// --- Recall: one WebSocket, reconnects by itself -------------------------------------------------
function useRecall(s: Settings) {
  const [up, setUp] = useState(false);
  const [ctx, setCtx] = useState<Ctx>({});
  const [goal, setGoal] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [interim, setInterim] = useState('');
  const [steps, setSteps] = useState<Step[]>([]);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!s.recallUrl) return;
    let stop = false, timer: ReturnType<typeof setTimeout>;
    const open = () => {
      const sock = new WebSocket(wsUrl(s.recallUrl, s.recallToken));
      ws.current = sock;
      sock.onopen = () => { setUp(true); sock.send(JSON.stringify({ cmd: 'refresh' })); };
      sock.onclose = () => { setUp(false); if (!stop) timer = setTimeout(open, 2000); };
      sock.onerror = () => sock.close();
      sock.onmessage = (e) => {
        let m: any; try { m = JSON.parse(String(e.data)); } catch { return; }
        const d = m.data;
        switch (m.type) {
          case 'snapshot':
            setCtx(d.ctx ?? {}); setGoal(d.eyes ?? null);
            setLines((d.utterances ?? []).slice(-40));
            setSteps((d.agents ?? []).map((a: any) => ({ ...a, from: 'recall' })));
            setPhotos(d.images ?? []);
            break;
          case 'ctx': setCtx(d); setGoal(d.eyes ?? null); break;
          case 'utterance': setLines((l) => [...l, d].slice(-40)); setInterim(''); break;
          case 'interim': setInterim(d.text ?? ''); break;
          case 'agent': setSteps((x) => [...x, { ...d, from: 'recall' }].slice(-80)); break;
          case 'image': setPhotos((p) => [...p, d].slice(-6)); break;
          case 'caption': setPhotos((p) => p.map((x) => (x.id === d.id ? { ...x, caption: d.caption } : x))); break;
          case 'event':
            setSteps((x) => [...x, { ts: d.ts, agent: 'Band', state: d.kind, detail: d.detail ?? '', from: 'recall' as const }].slice(-80));
            break;
        }
      };
    };
    open();
    return () => { stop = true; clearTimeout(timer); ws.current?.close(); };
  }, [s.recallUrl, s.recallToken]);

  const send = useCallback((cmd: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(cmd));
  }, []);
  return { up, ctx, goal, lines, interim, steps, photos, send };
}

// --- Team backend: poll /api/state (read only) ------------------------------------------------
function useBackend(s: Settings) {
  const [state, setState] = useState<any>(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    if (!s.backendUrl) { setState(null); return; }
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch(s.backendUrl.replace(/\/+$/, '') + '/api/state',
          { headers: s.backendToken ? { Authorization: `Bearer ${s.backendToken}` } : {} });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const j = await r.json();
        if (alive) { setState(j); setErr(''); }
      } catch (e: any) { if (alive) setErr(e?.message ?? 'offline'); }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(id); };
  }, [s.backendUrl, s.backendToken]);
  const steps: Step[] = (state?.events ?? []).map((e: any) => ({
    ts: e.ts / 1000, agent: e.agent, state: e.event, detail: e.detail ?? e.reason ?? '', from: 'backend' as const,
  }));
  const photo: Photo | null = state?.image?.jpeg_b64
    ? { id: 'backend-' + state.image.ts, ts: state.image.ts / 1000, source: 'backend ' + (state.image.scene ?? ''), caption: 'Team backend vision', jpeg_b64: state.image.jpeg_b64 }
    : null;
  return { up: !!state && !err, err, state, steps, photo };
}

// --- UI ------------------------------------------------------------------------------------------
function Dot({ color }: { color: string }) {
  return <View style={[st.dot, { backgroundColor: color }]} />;
}

function Btn({ label, onPress, tone = 'normal', disabled }: { label: string; onPress: () => void; tone?: 'normal' | 'go' | 'stop'; disabled?: boolean }) {
  const bg = tone === 'go' ? C.burst : tone === 'stop' ? C.bad : C.line;
  return (
    <Pressable onPress={onPress} disabled={disabled}
      style={({ pressed }) => [st.btn, { backgroundColor: bg, opacity: disabled ? 0.4 : pressed ? 0.7 : 1 }]}>
      <Text style={st.btnText}>{label}</Text>
    </Pressable>
  );
}

function DeviceCard({ title, color, status, rows, children }: { title: string; color: string; status: string; rows: string[]; children?: React.ReactNode }) {
  return (
    <View style={[st.card, { flex: 1 }]}>
      <View style={st.row}><Dot color={color} /><Text style={st.cardTitle}>{title}</Text></View>
      <Text style={[st.status, { color }]}>{status}</Text>
      {rows.filter(Boolean).map((r) => <Text key={r} style={st.small}>{r}</Text>)}
      <View style={st.btnRow}>{children}</View>
    </View>
  );
}

function SettingsModal({ open, value, onSave, onClose }: { open: boolean; value: Settings; onSave: (s: Settings) => void; onClose: () => void }) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value, open]);
  const field = (k: keyof Settings, label: string, hint: string, secret = false) => (
    <View style={{ marginBottom: 14 }}>
      <Text style={st.label}>{label}</Text>
      <TextInput style={st.input} value={v[k]} onChangeText={(t) => setV({ ...v, [k]: t })} placeholder={hint}
        placeholderTextColor={C.dim} autoCapitalize="none" autoCorrect={false} secureTextEntry={secret} />
    </View>
  );
  return (
    <Modal visible={open} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={[st.screen, { padding: 20 }]}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <Text style={st.h1}>Debug override</Text>
          <Text style={[st.small, { marginBottom: 18 }]}>
            Not needed for the demo: the signed build already knows the team backend and its tokens. Use this only to
            point the app somewhere else (a local backend, Recall). Empty fields keep the built-in values.
          </Text>
          {field('recallUrl', 'Recall address', 'https://….trycloudflare.com')}
          {field('recallToken', 'Recall token', 'RECALL_TOKEN', true)}
          {field('backendUrl', 'Team backend address (optional)', 'https://…')}
          {field('backendToken', 'Backend dashboard token (optional)', 'DASHBOARD_TOKENS entry', true)}
          {field('glassesUrl', 'Glasses link (backend /ws)', 'wss://…/ws?token=<glasses relay token>', true)}
          {field('bandUrl', 'Band link (backend /ws)', 'wss://…/ws?token=<band relay token>', true)}
          <View style={st.btnRow}>
            <Btn label="Save" tone="go" onPress={() => { onSave(v); onClose(); }} />
            <Btn label="Cancel" onPress={onClose} />
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Modal>
  );
}

function Main() {
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [showSettings, setShowSettings] = useState(false);
  const [goalText, setGoalText] = useState('');
  const [tab, setTab] = useState<'agents' | 'photos'>('agents');

  // Settings are a hidden debug override (long-press the title); the app works without ever opening them.
  useEffect(() => {
    // Only non-empty overrides win over the built-in values.
    AsyncStorage.getItem(KEY).then((raw) => {
      if (raw) setSettings({ ...DEFAULTS, ...Object.fromEntries(Object.entries(JSON.parse(raw)).filter(([, v]) => v)) });
    }).catch(() => {});
  }, []);
  const save = (s: Settings) => { setSettings(s); AsyncStorage.setItem(KEY, JSON.stringify(s)).catch(() => {}); };

  const recall = useRecall(settings);                  // debug only: off unless a Recall address was set
  const backend = useBackend(settings);
  // This phone is the hub (iOS build): glasses over Meta DAT and the band over Bluetooth, both straight to
  // the team backend's /ws as contract v0 clients.
  const phone = useGlasses(settings.glassesUrl, '');
  const phoneBand = useBand(settings.bandUrl, '');
  const { ctx } = recall;

  const steps = useMemo(() => [...recall.steps, ...backend.steps].sort((a, b) => b.ts - a.ts).slice(0, 60),
    [recall.steps, backend.steps]);
  const photos = useMemo(() => [...recall.photos, ...(backend.photo ? [backend.photo] : [])].sort((a, b) => b.ts - a.ts),
    [recall.photos, backend.photo]);
  const latest = photos[0];

  const native = phone.available;
  const clients: string[] = backend.state?.clients ?? [];
  const act = backend.state?.activity ?? {};
  const bandUp = native ? phoneBand.state === 'connected' : clients.includes('band') || (recall.up && !!ctx.connected);
  const bandBusy = phoneBand.state === 'scanning' || phoneBand.state === 'connecting' || phoneBand.state === 'reconnecting';
  const glassesState: string = native ? phone.glasses : (backend.state?.streaming ? 'streaming' : clients.includes('glasses') ? 'connected' : 'disconnected');
  const glassesUp = glassesState !== 'disconnected';
  const heard: { ts: number; text: string }[] = recall.lines.length
    ? recall.lines.slice(-4)
    : backend.steps.filter((s) => s.state === 'transcript').slice(0, 4).reverse().map((s) => ({ ts: s.ts, text: s.detail }));

  return (
    <SafeAreaView style={st.screen} edges={['top', 'left', 'right']}>
      <StatusBar style="light" />
      <View style={[st.row, st.header]}>
        <Pressable onLongPress={() => setShowSettings(true)} delayLongPress={1500}>
          <Text style={st.h1}>BrightBlind</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        <Dot color={backend.up ? C.ok : C.bad} /><Text style={st.small}>{backend.up ? 'agents online' : backend.err || 'agents offline'}</Text>
      </View>

      <ScrollView style={{ flexGrow: 0, maxHeight: '52%' }} contentContainerStyle={{ padding: 12, gap: 10 }}>
        <View style={st.cards}>
          <DeviceCard title="Vexo band" color={bandUp ? C.ok : bandBusy ? C.warn : C.bad}
            status={native ? (phoneBand.state === 'idle' ? 'not connected' : phoneBand.state === 'scanning' ? 'looking… double-tap the band' : phoneBand.state)
              : bandUp ? 'connected' : 'not connected'}
            rows={[
              native && phoneBand.state === 'connected'
                ? `${phoneBand.activity ?? '–'} · ${phoneBand.steps ?? 0} steps${phoneBand.battery != null ? ` · ${phoneBand.battery}%` : ''}`
                : act.state ? `${act.state} · ${act.steps ?? 0} steps` : '',
              native && phoneBand.state !== 'idle' ? `agents link ${phoneBand.socket}` : '',
              phoneBand.error ?? '']}>
            {native ? (phoneBand.state === 'idle' || phoneBand.state === 'error'
              ? <Btn label="Connect" tone="go" onPress={() => phoneBand.connect()} />
              : <Btn label="Disconnect" onPress={() => phoneBand.disconnect()} />) : null}
          </DeviceCard>
          <DeviceCard title="Meta glasses" color={glassesUp ? (glassesState === 'streaming' ? C.burst : C.ok) : C.bad}
            status={glassesState === 'disconnected' ? 'not connected' : glassesState}
            rows={[native ? `agents link ${phone.link}` : '', backend.state?.scene ? `scene: ${backend.state.scene}` : '']}>
            {native && phone.glasses === 'disconnected' ? <>
              <Btn label="Connect" tone="go" onPress={() => phone.connect()} />
              <Btn label="Register" onPress={() => phone.register()} />
              <Btn label="Camera" onPress={() => phone.requestCameraPermission()} />
            </> : null}
            {native && glassesUp ? (
              // No manual Photo: the backend only accepts photos it asked for (a double-tap asks).
              <Btn label="Test voice" onPress={() => phone.say('BrightBlind is ready.')} />
            ) : null}
          </DeviceCard>
        </View>

        {recall.up ? (
          <View style={st.card}>
            <Text style={st.cardTitle}>Photo burst (Recall)</Text>
            <View style={[st.row, { gap: 8, marginTop: 8 }]}>
              <TextInput style={[st.input, { flex: 1 }]} value={goalText} onChangeText={setGoalText}
                placeholder={recall.goal ?? 'what to find'} placeholderTextColor={C.dim} />
              {recall.goal
                ? <Btn label="Stop" tone="stop" onPress={() => recall.send({ cmd: 'burst', on: false })} />
                : <Btn label="Start" tone="go" disabled={!goalText.trim()}
                    onPress={() => { recall.send({ cmd: 'burst', on: true, text: goalText }); setGoalText(''); }} />}
            </View>
          </View>
        ) : null}

        <View style={st.card}>
          <Text style={st.cardTitle}>Heard</Text>
          {heard.map((l, i) => (
            <Text key={`${l.ts}-${i}`} style={st.heard}><Text style={st.dim}>{clock(l.ts)}  </Text>{l.text}</Text>
          ))}
          {recall.interim ? <Text style={[st.heard, st.dim]}>… {recall.interim}</Text> : null}
          {!heard.length && !recall.interim ? <Text style={st.small}>Nothing yet. Connect the band and talk.</Text> : null}
          {backend.state?.target
            ? <Text style={[st.small, { marginTop: 6 }]}>Looking for: {backend.state.target}{backend.state.streaming ? ' · camera on' : ''}</Text>
            : null}
        </View>
      </ScrollView>

      <View style={st.dock}>
        <View style={[st.row, { gap: 6, paddingHorizontal: 12, paddingTop: 10 }]}>
          {(['agents', 'photos'] as const).map((t) => (
            <Pressable key={t} onPress={() => setTab(t)} style={[st.tab, tab === t && st.tabOn]}>
              <Text style={[st.tabText, tab === t && { color: C.text }]}>{t === 'agents' ? 'What the agents do' : `Photos (${photos.length})`}</Text>
            </Pressable>
          ))}
        </View>

        {latest ? (
          <View style={[st.row, st.latest]}>
            <Image source={{ uri: `data:image/jpeg;base64,${latest.jpeg_b64}` }} style={st.thumb} resizeMode="cover" />
            <View style={{ flex: 1 }}>
              <Text style={[st.small, { color: latest.source === 'burst' ? C.burst : C.warn }]}>
                {latest.source} photo · {clock(latest.ts)}
              </Text>
              <Text style={st.caption} numberOfLines={3}>{latest.caption}</Text>
            </View>
          </View>
        ) : null}

        <ScrollView contentContainerStyle={{ padding: 12, paddingBottom: 40, gap: 6 }}>
          {tab === 'agents'
            ? steps.length
              ? steps.map((s, i) => (
                <View key={`${s.from}-${s.ts}-${i}`} style={st.step}>
                  <Text style={[st.stepAgent, { color: AGENT_COLOR[s.agent.split(' ')[0]] ?? (s.from === 'backend' ? C.warn : C.dim) }]}>
                    {s.agent}{s.from === 'backend' ? ' ·team' : ''}
                  </Text>
                  <Text style={st.stepText}><Text style={{ fontWeight: '700' }}>{s.state}</Text>{s.detail ? `  ${s.detail}` : ''}</Text>
                  <Text style={st.stepTime}>{clock(s.ts)}</Text>
                </View>))
              : <Text style={st.small}>No agent activity yet. Say "help me find …" near the band.</Text>
            : photos.length
              ? photos.map((p) => (
                <View key={String(p.id)} style={{ marginBottom: 10 }}>
                  <Image source={{ uri: `data:image/jpeg;base64,${p.jpeg_b64}` }} style={st.photo} resizeMode="contain" />
                  <Text style={st.small}>{p.source} · {clock(p.ts)}</Text>
                  <Text style={st.caption}>{p.caption}</Text>
                </View>))
              : <Text style={st.small}>No photo yet. Tap the band or start a burst.</Text>}
        </ScrollView>
      </View>

      <SettingsModal open={showSettings} value={settings} onSave={save} onClose={() => setShowSettings(false)} />
    </SafeAreaView>
  );
}

export default function App() {
  return <SafeAreaProvider><Main /></SafeAreaProvider>;
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.line },
  h1: { color: C.text, fontSize: 22, fontWeight: '800' },
  row: { flexDirection: 'row', alignItems: 'center' },
  dot: { width: 9, height: 9, borderRadius: 5, marginRight: 6 },
  link: { color: C.accent, fontWeight: '700', fontSize: 15 },
  cards: { flexDirection: 'row', gap: 10 },
  card: { backgroundColor: C.card, borderRadius: 14, padding: 12, borderWidth: 1, borderColor: C.line },
  cardTitle: { color: C.text, fontWeight: '700', fontSize: 15 },
  status: { fontSize: 13, fontWeight: '600', marginTop: 4, marginBottom: 2 },
  small: { color: C.dim, fontSize: 12 },
  dim: { color: C.dim },
  heard: { color: C.text, fontSize: 14, marginTop: 4 },
  btnRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 },
  btn: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10 },
  btnText: { color: C.text, fontWeight: '700', fontSize: 13 },
  label: { color: C.text, fontWeight: '600', marginBottom: 6 },
  input: { backgroundColor: C.bg, color: C.text, borderRadius: 10, borderWidth: 1, borderColor: C.line, paddingHorizontal: 10, paddingVertical: 8, fontSize: 14 },
  dock: { flex: 1, backgroundColor: C.card, borderTopLeftRadius: 18, borderTopRightRadius: 18, borderTopWidth: 1, borderColor: C.line },
  tab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: C.bg },
  tabOn: { backgroundColor: C.line },
  tabText: { color: C.dim, fontWeight: '700', fontSize: 13 },
  latest: { gap: 10, marginHorizontal: 12, marginTop: 10, padding: 8, borderRadius: 12, backgroundColor: C.bg },
  thumb: { width: 72, height: 96, borderRadius: 8, backgroundColor: C.line },
  caption: { color: C.text, fontSize: 13, marginTop: 2 },
  photo: { width: '100%', height: 260, borderRadius: 10, backgroundColor: C.bg },
  step: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  stepAgent: { width: 84, fontWeight: '800', fontSize: 12 },
  stepText: { flex: 1, color: C.text, fontSize: 13 },
  stepTime: { color: C.dim, fontSize: 11 },
});
