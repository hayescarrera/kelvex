/** Domain types for the mocked data layer. Mirrors the real API shapes. */

export type Severity = "critical" | "warning" | "info";
export type AlarmState = "active" | "acknowledged" | "snoozed" | "resolved";
export type AssetKind = "compressor" | "evaporator" | "condenser" | "case" | "blast_freezer";
export type Provenance = "raw" | "derived" | "interpolated";
export type LeakStage = "detection" | "verification" | "repair" | "reverification" | "closed";

export interface Site {
  id: string;
  name: string;
  city: string;
  tz: string;
  kind: "grocery" | "cold_storage";
}

export interface Room {
  id: string;
  siteId: string;
  name: string;
  targetF: number;
}

export interface Asset {
  id: string;
  siteId: string;
  roomId: string;
  name: string;
  kind: AssetKind;
  circuitId: string | null;
  running: boolean;
  inDefrost: boolean;
  defrostProgress: number; // 0..1 while inDefrost
  runtimeHours: number;
  cyclesToday: number;
  setpoint: { label: string; value: number; kind: "temp" | "pressure" } | null;
}

export interface SensorPoint {
  id: string;
  assetId: string;
  metric: string;              // suction_pressure | discharge_pressure | temp | superheat | kw
  kind: "temp" | "pressure" | "percent" | "kw";
  value: number;
  lastUpdate: number;          // epoch ms
  provenance: Provenance;
  device: string;              // source device name
  /** minutes without report before the value is treated as stale */
  staleAfterMin: number;
}

export interface Alarm {
  id: string;
  siteId: string;
  assetId: string;
  severity: Severity;
  state: AlarmState;
  title: string;
  detail: string;
  raisedAt: number;
  ackBy: string | null;
  assignee: string | null;
  notes: string[];
}

export interface LeakEvent {
  id: string;
  siteId: string;
  circuitId: string;
  circuitName: string;
  stage: LeakStage;
  detectedAt: number;
  repairDeadline: number;      // detectedAt + 30d
  lbsLost: number;
  stagesDone: Partial<Record<LeakStage, number>>; // stage -> completed at
  missingToClose: string[];
}

export interface Circuit {
  id: string;
  siteId: string;
  name: string;
  refrigerant: string;
  fullChargeLbs: number;
  addedLbs365: number;
}

export interface LedgerEntry {
  id: string;
  siteId: string;
  circuitId: string;
  ts: number;
  kind: "addition" | "recovery";
  lbs: number;
  tech: string;
  epaCert: string;
  cylinder: string;
}

export interface Agent {
  id: string;
  siteId: string;
  name: string;
  state: "connected" | "stale" | "disconnected";
  lastCheckin: number;
  version: string;
  discoveredPoints: number;
  mappedPoints: number;
}
