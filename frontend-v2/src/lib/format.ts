/**
 * Unit conversion + formatting. All telemetry is stored in base units
 * (°F, psi, lb) — the same convention as the backend — and converted at
 * the presentation edge based on user prefs.
 */
import type { Prefs } from "../state/prefs";

export type Kind = "temp" | "pressure" | "mass" | "percent" | "kw" | "count";

export function convert(value: number, kind: Kind, p: Prefs): number {
  switch (kind) {
    case "temp":
      return p.tempUnit === "C" ? ((value - 32) * 5) / 9 : value;
    case "pressure":
      return p.pressureUnit === "kPa" ? value * 6.89476 : value;
    case "mass":
      return p.massUnit === "kg" ? value * 0.453592 : value;
    default:
      return value;
  }
}

export function unitLabel(kind: Kind, p: Prefs): string {
  switch (kind) {
    case "temp": return `°${p.tempUnit}`;
    case "pressure": return p.pressureUnit;
    case "mass": return p.massUnit;
    case "percent": return "%";
    case "kw": return "kW";
    case "count": return "";
  }
}

export function fmtValue(value: number | null, kind: Kind, p: Prefs, decimals = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const v = convert(value, kind, p);
  return v.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Timestamps: explicit about which zone — compliance depends on it. */
export function fmtTime(ts: number, p: Prefs, siteTz: string): string {
  const zone = p.tzMode === "site" ? siteTz : Intl.DateTimeFormat().resolvedOptions().timeZone;
  return new Intl.DateTimeFormat("en-US", {
    timeZone: zone, month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  }).format(ts);
}

export function tzBadge(p: Prefs, siteTz: string): string {
  return p.tzMode === "site" ? `site (${siteTz.split("/")[1]?.replace("_", " ")})` : "your time";
}

export function ago(ts: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export function daysLeft(deadline: number, now = Date.now()): number {
  return Math.ceil((deadline - now) / 86_400_000);
}
