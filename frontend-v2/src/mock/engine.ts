/**
 * Mock telemetry engine — lets the whole product demo cold, no backend.
 *
 * Simulates: live sensor drift on a 2s tick, a compressor that cycles, a
 * defrost that visibly advances, one sensor that went quiet 22 minutes ago
 * (stale rendering), periodic alarm firing, and an open leak event with a
 * live 30-day repair clock sitting at 6 days (urgent styling threshold).
 *
 * The store is a plain event-emitter snapshot store (works with
 * useSyncExternalStore); history is a ring buffer per sensor so charts can
 * render 100k+ points via uPlot without re-allocating.
 */
import type {
  Agent, Alarm, Asset, Circuit, LeakEvent, LedgerEntry, Room, SensorPoint, Site,
} from "./types";

const now = Date.now();
const HOUR = 3_600_000;
const DAY = 86_400_000;

// ── Fleet definition ─────────────────────────────────────────────────
export const sites: Site[] = [
  { id: "s-chi", name: "Chicago DC", city: "Chicago, IL", tz: "America/Chicago", kind: "cold_storage" },
  { id: "s-dal", name: "Dallas DC", city: "Dallas, TX", tz: "America/Chicago", kind: "cold_storage" },
  { id: "s-mke", name: "Store #12 — Milwaukee", city: "Milwaukee, WI", tz: "America/Chicago", kind: "grocery" },
];

export const rooms: Room[] = [
  { id: "r-chi-frz", siteId: "s-chi", name: "Freezer Hall A", targetF: -10 },
  { id: "r-chi-dock", siteId: "s-chi", name: "Dock Zone 3", targetF: 34 },
  { id: "r-chi-blast", siteId: "s-chi", name: "Blast Cell 1", targetF: -30 },
  { id: "r-dal-frz", siteId: "s-dal", name: "Freezer Hall", targetF: -5 },
  { id: "r-dal-cool", siteId: "s-dal", name: "Cooler 2", targetF: 36 },
  { id: "r-mke-dairy", siteId: "s-mke", name: "Dairy Cases", targetF: 37 },
  { id: "r-mke-frz", siteId: "s-mke", name: "Frozen Aisle", targetF: -8 },
];

export const circuits: Circuit[] = [
  { id: "c-chi-a", siteId: "s-chi", name: "Rack A — Ammonia", refrigerant: "R-717", fullChargeLbs: 2400, addedLbs365: 0 },
  { id: "c-chi-b", siteId: "s-chi", name: "Rack B — Freezer", refrigerant: "R-448A", fullChargeLbs: 1240, addedLbs365: 262 },
  { id: "c-dal-a", siteId: "s-dal", name: "Rack A", refrigerant: "R-407A", fullChargeLbs: 980, addedLbs365: 71 },
  { id: "c-mke-a", siteId: "s-mke", name: "Rack A — Sales Floor", refrigerant: "R-448A", fullChargeLbs: 610, addedLbs365: 48 },
];

export const assets: Asset[] = [
  { id: "a-chi-c1", siteId: "s-chi", roomId: "r-chi-frz", name: "Compressor C-1", kind: "compressor", circuitId: "c-chi-b", running: true, inDefrost: false, defrostProgress: 0, runtimeHours: 31240, cyclesToday: 6, setpoint: { label: "Suction", value: 22, kind: "pressure" } },
  { id: "a-chi-c2", siteId: "s-chi", roomId: "r-chi-frz", name: "Compressor C-2", kind: "compressor", circuitId: "c-chi-b", running: true, inDefrost: false, defrostProgress: 0, runtimeHours: 28911, cyclesToday: 9, setpoint: { label: "Suction", value: 22, kind: "pressure" } },
  { id: "a-chi-c3", siteId: "s-chi", roomId: "r-chi-frz", name: "Compressor C-3", kind: "compressor", circuitId: "c-chi-b", running: false, inDefrost: false, defrostProgress: 0, runtimeHours: 40102, cyclesToday: 14, setpoint: { label: "Suction", value: 22, kind: "pressure" } },
  { id: "a-chi-ev1", siteId: "s-chi", roomId: "r-chi-frz", name: "Evaporator E-1", kind: "evaporator", circuitId: "c-chi-b", running: true, inDefrost: true, defrostProgress: 0.35, runtimeHours: 30300, cyclesToday: 4, setpoint: { label: "Room", value: -10, kind: "temp" } },
  { id: "a-chi-bl1", siteId: "s-chi", roomId: "r-chi-blast", name: "Blast Freezer BF-1", kind: "blast_freezer", circuitId: "c-chi-a", running: true, inDefrost: false, defrostProgress: 0, runtimeHours: 12800, cyclesToday: 2, setpoint: { label: "Cell", value: -30, kind: "temp" } },
  { id: "a-chi-dk1", siteId: "s-chi", roomId: "r-chi-dock", name: "Dock Cooler DK-1", kind: "case", circuitId: "c-chi-b", running: true, inDefrost: false, defrostProgress: 0, runtimeHours: 8100, cyclesToday: 3, setpoint: { label: "Zone", value: 34, kind: "temp" } },
  { id: "a-dal-c1", siteId: "s-dal", roomId: "r-dal-frz", name: "Compressor C-1", kind: "compressor", circuitId: "c-dal-a", running: true, inDefrost: false, defrostProgress: 0, runtimeHours: 22110, cyclesToday: 7, setpoint: { label: "Suction", value: 26, kind: "pressure" } },
  { id: "a-dal-cs1", siteId: "s-dal", roomId: "r-dal-cool", name: "Cooler Circuit CS-1", kind: "case", circuitId: "c-dal-a", running: true, inDefrost: false, defrostProgress: 0, runtimeHours: 19040, cyclesToday: 3, setpoint: { label: "Case", value: 36, kind: "temp" } },
  { id: "a-mke-c1", siteId: "s-mke", roomId: "r-mke-frz", name: "Compressor C-1", kind: "compressor", circuitId: "c-mke-a", running: true, inDefrost: false, defrostProgress: 0, runtimeHours: 51000, cyclesToday: 11, setpoint: { label: "Suction", value: 24, kind: "pressure" } },
  { id: "a-mke-cs4", siteId: "s-mke", roomId: "r-mke-dairy", name: "Case Line-up 4", kind: "case", circuitId: "c-mke-a", running: true, inDefrost: false, defrostProgress: 0, runtimeHours: 47720, cyclesToday: 5, setpoint: { label: "Case", value: 37, kind: "temp" } },
];

/** metric templates per asset kind */
const metricDefs: Record<string, Array<{ metric: string; kind: SensorPoint["kind"]; base: (a: Asset) => number; jitter: number }>> = {
  compressor: [
    { metric: "suction_pressure", kind: "pressure", base: () => 23, jitter: 1.4 },
    { metric: "discharge_pressure", kind: "pressure", base: () => 176, jitter: 4 },
    { metric: "discharge_temp", kind: "temp", base: () => 182, jitter: 3 },
    { metric: "kw", kind: "kw", base: (a) => (a.running ? 138 : 0), jitter: 8 },
    { metric: "superheat", kind: "temp", base: () => 12, jitter: 1.2 },
  ],
  evaporator: [
    { metric: "coil_temp", kind: "temp", base: () => -14, jitter: 1.2 },
    { metric: "room_temp", kind: "temp", base: () => -9.5, jitter: 0.6 },
  ],
  condenser: [
    { metric: "cond_pressure", kind: "pressure", base: () => 168, jitter: 3 },
  ],
  case: [
    { metric: "case_temp", kind: "temp", base: () => 36.5, jitter: 0.5 },
    { metric: "product_temp", kind: "temp", base: () => 37.2, jitter: 0.3 },
  ],
  blast_freezer: [
    { metric: "cell_temp", kind: "temp", base: () => -29, jitter: 1.1 },
    { metric: "kw", kind: "kw", base: () => 96, jitter: 6 },
  ],
};

// ── Live sensor state + history ring buffers ─────────────────────────
export const sensors: SensorPoint[] = [];
const HISTORY_POINTS = 2_000;           // per sensor @2s tick ≈ 66 min live + seeded 24h
export const history = new Map<string, { t: Float64Array; v: Float64Array; head: number; filled: boolean }>();

for (const a of assets) {
  for (const def of metricDefs[a.kind] ?? []) {
    const id = `${a.id}:${def.metric}`;
    sensors.push({
      id, assetId: a.id, metric: def.metric, kind: def.kind,
      value: def.base(a), lastUpdate: now,
      provenance: def.metric === "superheat" ? "derived" : "raw",
      device: a.kind === "compressor" ? "Danfoss AK-SC 255" : "Modbus PLC #2",
      staleAfterMin: 10,
    });
    // Seed 24h of history at 45s cadence so charts open with real shape
    const t = new Float64Array(HISTORY_POINTS);
    const v = new Float64Array(HISTORY_POINTS);
    const seedCount = HISTORY_POINTS;
    for (let i = 0; i < seedCount; i++) {
      const ts = now - (seedCount - i) * 45_000;
      const daily = Math.sin((ts % DAY) / DAY * Math.PI * 2) * def.jitter * 1.5;
      v[i] = def.base(a) + daily + (Math.random() - 0.5) * def.jitter;
      t[i] = ts / 1000;
    }
    history.set(id, { t, v, head: 0, filled: true });
  }
}

// The dangerous failure mode, on purpose: one sensor went quiet 22 min ago.
const staleSensor = sensors.find((s) => s.id === "a-mke-cs4:product_temp")!;
staleSensor.lastUpdate = now - 22 * 60_000;

// ── Alarms ───────────────────────────────────────────────────────────
export const alarms: Alarm[] = [
  {
    id: "al-1", siteId: "s-chi", assetId: "a-chi-c3", severity: "warning", state: "active",
    title: "Compressor C-3 short-cycling", detail: "14 starts/hr against a baseline of 6. Possible low charge or control hunting.",
    raisedAt: now - 52 * 60_000, ackBy: null, assignee: null, notes: [],
  },
  {
    id: "al-2", siteId: "s-mke", assetId: "a-mke-cs4", severity: "critical", state: "active",
    title: "Case Line-up 4 product sensor offline", detail: "No report for 22 minutes. Last known 37.2°F. Product temp is unverified.",
    raisedAt: now - 20 * 60_000, ackBy: null, assignee: null, notes: [],
  },
  {
    id: "al-3", siteId: "s-dal", assetId: "a-dal-cs1", severity: "info", state: "acknowledged",
    title: "Defrost completed late", detail: "Cycle exceeded schedule by 11 minutes; terminated on temperature.",
    raisedAt: now - 6 * HOUR, ackBy: "M. Ruiz", assignee: null, notes: ["Watching next cycle."],
  },
];

// ── Leak events (the compliance heart) ───────────────────────────────
export const leakEvents: LeakEvent[] = [
  {
    id: "lk-1", siteId: "s-chi", circuitId: "c-chi-b", circuitName: "Rack B — Freezer",
    stage: "repair",
    detectedAt: now - 24 * DAY,
    repairDeadline: now - 24 * DAY + 30 * DAY,   // 6 days left — urgent
    lbsLost: 262,
    stagesDone: { detection: now - 24 * DAY, verification: now - 22 * DAY },
    missingToClose: ["Repair record with technician signature", "Initial verification test", "Follow-up verification test (30 days)"],
  },
  {
    id: "lk-2", siteId: "s-dal", circuitId: "c-dal-a", circuitName: "Rack A",
    stage: "closed",
    detectedAt: now - 90 * DAY,
    repairDeadline: now - 60 * DAY,
    lbsLost: 71,
    stagesDone: {
      detection: now - 90 * DAY, verification: now - 88 * DAY,
      repair: now - 84 * DAY, reverification: now - 54 * DAY, closed: now - 54 * DAY,
    },
    missingToClose: [],
  },
];

export const ledger: LedgerEntry[] = [
  { id: "lg-1", siteId: "s-chi", circuitId: "c-chi-b", ts: now - 23 * DAY, kind: "addition", lbs: 120, tech: "Pat Doe", epaCert: "EPA-608-12345", cylinder: "CYL-8841" },
  { id: "lg-2", siteId: "s-chi", circuitId: "c-chi-b", ts: now - 11 * DAY, kind: "addition", lbs: 142, tech: "Pat Doe", epaCert: "EPA-608-12345", cylinder: "CYL-8852" },
  { id: "lg-3", siteId: "s-dal", circuitId: "c-dal-a", ts: now - 84 * DAY, kind: "addition", lbs: 71, tech: "J. Okafor", epaCert: "EPA-608-55901", cylinder: "CYL-7310" },
  { id: "lg-4", siteId: "s-dal", circuitId: "c-dal-a", ts: now - 84 * DAY, kind: "recovery", lbs: 4.5, tech: "J. Okafor", epaCert: "EPA-608-55901", cylinder: "RCV-2210" },
  { id: "lg-5", siteId: "s-mke", circuitId: "c-mke-a", ts: now - 200 * DAY, kind: "addition", lbs: 48, tech: "javier@coolserv.com", epaCert: "EPA-608-88112", cylinder: "CYL-5518" },
];

export const agents: Agent[] = [
  { id: "ag-1", siteId: "s-chi", name: "chi-gw-01", state: "connected", lastCheckin: now - 21_000, version: "1.4.2", discoveredPoints: 148, mappedPoints: 141 },
  { id: "ag-2", siteId: "s-dal", name: "dal-gw-01", state: "connected", lastCheckin: now - 34_000, version: "1.4.2", discoveredPoints: 96, mappedPoints: 96 },
  { id: "ag-3", siteId: "s-mke", name: "mke-gw-01", state: "stale", lastCheckin: now - 22 * 60_000, version: "1.3.9", discoveredPoints: 61, mappedPoints: 55 },
];

// ── Tick loop + subscriptions ────────────────────────────────────────
type Listener = () => void;
const listeners = new Set<Listener>();
let version = 0;

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
export function getVersion() { return version; }

function emit() {
  version++;
  for (const fn of listeners) fn();
}

let started = false;
export function startEngine() {
  if (started) return;
  started = true;

  setInterval(() => {
    const t = Date.now();
    for (const s of sensors) {
      if (s === staleSensor) continue;                 // stays silent
      if (agents.find((a) => a.siteId === "s-mke")?.state === "stale" && s.assetId.startsWith("a-mke")) {
        continue;                                       // whole site degrades with its gateway
      }
      const def = metricDefs[assets.find((a) => a.id === s.assetId)!.kind]
        ?.find((d) => d.metric === s.metric);
      if (!def) continue;
      const asset = assets.find((a) => a.id === s.assetId)!;
      const target = def.base(asset);
      // mean-reverting random walk — looks like real telemetry, not noise
      s.value = s.value + (target - s.value) * 0.06 + (Math.random() - 0.5) * def.jitter * 0.4;
      s.lastUpdate = t;
      const h = history.get(s.id)!;
      h.t[h.head] = t / 1000;
      h.v[h.head] = s.value;
      h.head = (h.head + 1) % h.t.length;
    }

    // Defrost visibly advances, completes, and restarts hours later
    const ev = assets.find((a) => a.id === "a-chi-ev1")!;
    if (ev.inDefrost) {
      ev.defrostProgress = Math.min(1, ev.defrostProgress + 0.004);
      if (ev.defrostProgress >= 1) { ev.inDefrost = false; ev.defrostProgress = 0; }
    }

    // Compressor C-3 occasionally short-cycles on/off (it has the alarm)
    if (Math.random() < 0.02) {
      const c3 = assets.find((a) => a.id === "a-chi-c3")!;
      c3.running = !c3.running;
      if (c3.running) c3.cyclesToday++;
    }

    emit();
  }, 2000);

  // A fresh warning fires a few minutes into the demo, once.
  setTimeout(() => {
    alarms.unshift({
      id: "al-live-1", siteId: "s-chi", assetId: "a-chi-ev1", severity: "warning", state: "active",
      title: "Evaporator E-1 defrost overrun", detail: "Defrost cycle running long; terminate-on-temp not reached.",
      raisedAt: Date.now(), ackBy: null, assignee: null, notes: [],
    });
    emit();
  }, 90_000);
}

/** Chart series for a sensor, ordered oldest→newest (uPlot format). */
export function seriesFor(sensorId: string): [number[], number[]] {
  const h = history.get(sensorId);
  if (!h) return [[], []];
  const ts: number[] = []; const vs: number[] = [];
  const n = h.t.length;
  for (let i = 0; i < n; i++) {
    const idx = (h.head + i) % n;
    if (h.t[idx] > 0) { ts.push(h.t[idx]); vs.push(h.v[idx]); }
  }
  return [ts, vs];
}

// ── Mutations (in-memory; mirror real API actions) ───────────────────
export function ackAlarm(id: string, who = "you") {
  const a = alarms.find((x) => x.id === id);
  if (a && a.state === "active") { a.state = "acknowledged"; a.ackBy = who; emit(); }
}
export function snoozeAlarm(id: string) {
  const a = alarms.find((x) => x.id === id);
  if (a) { a.state = "snoozed"; emit(); }
}
export function assignAlarm(id: string, assignee: string) {
  const a = alarms.find((x) => x.id === id);
  if (a) { a.assignee = assignee; emit(); }
}
export function annotateAlarm(id: string, note: string) {
  const a = alarms.find((x) => x.id === id);
  if (a) { a.notes.push(note); emit(); }
}
export function isStale(s: SensorPoint, at = Date.now()): boolean {
  return at - s.lastUpdate > s.staleAfterMin * 60_000;
}

// ── Work-order lifecycle (alert → dispatched → in progress → closed) ──
export type WoState = "alert" | "dispatched" | "in_progress" | "closed";
export const workOrders = new Map<string, WoState>([
  ["al-1", "dispatched"],
  ["al-3", "closed"],
]);
export function woStateFor(alarmId: string): WoState {
  return workOrders.get(alarmId) ?? "alert";
}
export function advanceWorkOrder(alarmId: string) {
  const order: WoState[] = ["alert", "dispatched", "in_progress", "closed"];
  const cur = woStateFor(alarmId);
  const next = order[Math.min(order.indexOf(cur) + 1, order.length - 1)];
  workOrders.set(alarmId, next);
  emit();
}

// ── Site health score (0–100), the category-standard rollup ──────────
export function siteHealth(siteId: string): number {
  let score = 100;
  for (const a of alarms.filter((x) => x.siteId === siteId && x.state === "active")) {
    score -= a.severity === "critical" ? 25 : a.severity === "warning" ? 10 : 3;
  }
  for (const s of sensors) {
    const asset = assets.find((x) => x.id === s.assetId);
    if (asset?.siteId === siteId && isStale(s)) score -= 8;
  }
  for (const l of leakEvents.filter((x) => x.siteId === siteId && x.stage !== "closed")) {
    const days = (l.repairDeadline - Date.now()) / 86_400_000;
    score -= days < 0 ? 30 : days <= 7 ? 18 : 10;
  }
  const agent = agents.find((a) => a.siteId === siteId);
  if (agent && agent.state !== "connected") score -= 12;
  return Math.max(0, Math.round(score));
}

// ── Compressor failure probability (ranked queue, highest risk first) ─
const baseFailureProb: Record<string, number> = {
  "a-chi-c3": 0.62,  // short-cycling
  "a-mke-c1": 0.31,  // high runtime hours
  "a-chi-c2": 0.12,
  "a-chi-c1": 0.07,
  "a-dal-c1": 0.05,
};
export function failureProb(assetId: string): number | null {
  const p = baseFailureProb[assetId];
  return p == null ? null : Math.min(0.99, p + Math.sin(Date.now() / 600_000) * 0.02);
}
export function rankedCompressors() {
  return assets
    .filter((a) => a.kind === "compressor")
    .map((a) => ({ asset: a, prob: failureProb(a.id) ?? 0 }))
    .sort((x, y) => y.prob - x.prob);
}

// ── Needs-attention queue: everything urgent, ranked ─────────────────
export interface AttentionItem {
  id: string;
  rank: number;              // higher = more urgent
  kind: "alarm" | "leak" | "stale" | "compressor";
  title: string;
  detail: string;
  siteId: string;
  href: string;
}
export function needsAttention(): AttentionItem[] {
  const items: AttentionItem[] = [];
  for (const a of alarms.filter((x) => x.state === "active")) {
    items.push({
      id: `at-${a.id}`,
      rank: a.severity === "critical" ? 100 : a.severity === "warning" ? 60 : 20,
      kind: "alarm", title: a.title, detail: a.detail, siteId: a.siteId,
      href: "/alarms",
    });
  }
  for (const l of leakEvents.filter((x) => x.stage !== "closed")) {
    const days = Math.ceil((l.repairDeadline - Date.now()) / 86_400_000);
    items.push({
      id: `at-${l.id}`,
      rank: days < 0 ? 120 : days <= 7 ? 90 : 55,
      kind: "leak", title: `Repair window: ${days}d left on ${l.circuitName}`,
      detail: `${l.lbsLost} lb lost · ${l.missingToClose.length} items missing to close`,
      siteId: l.siteId, href: "/leaks",
    });
  }
  for (const { asset, prob } of rankedCompressors()) {
    if (prob >= 0.3) {
      items.push({
        id: `at-fp-${asset.id}`, rank: Math.round(prob * 80),
        kind: "compressor", title: `${asset.name} failure risk ${(prob * 100).toFixed(0)}%`,
        detail: "Ranked by failure probability from live health scoring",
        siteId: asset.siteId, href: `/assets/${asset.id}`,
      });
    }
  }
  return items.sort((a, b) => b.rank - a.rank);
}
