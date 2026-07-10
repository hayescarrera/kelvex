/**
 * Core primitives. These encode the non-negotiables:
 *  - status = icon + text + color (never color alone)
 *  - critical renders instantly (no transition, enforced in CSS)
 *  - stale is visibly stale, with timestamp
 *  - every number offers provenance on hover/tap
 *  - the repair clock is unmissable
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { usePrefs } from "../state/prefs";
import { ago, daysLeft, fmtValue, unitLabel, type Kind } from "../lib/format";
import type { SensorPoint } from "../mock/types";
import { isStale } from "../mock/engine";

// ── Status pill ──────────────────────────────────────────────────────
const GLYPHS: Record<string, string> = {
  critical: "▲", warning: "◆", ok: "●", info: "○", stale: "◌",
};
export function StatusPill({ level, label }: { level: "critical" | "warning" | "ok" | "info" | "stale"; label: string }) {
  return (
    <span className={`pill ${level}`} role="status" aria-label={`${level}: ${label}`}>
      <span className="glyph" aria-hidden>{GLYPHS[level]}</span>
      {label}
    </span>
  );
}

// ── Tweening number (snaps in Field mode / motion none) ─────────────
export function TweenNumber({ value, kind, decimals = 1 }: { value: number | null; kind: Kind; decimals?: number }) {
  const prefs = usePrefs();
  const tween = prefs.mode === "command" && prefs.motion === "full";
  const [shown, setShown] = useState(value);
  const raf = useRef(0);

  useEffect(() => {
    if (value == null || shown == null || !tween) { setShown(value); return; }
    const from = shown, to = value, t0 = performance.now(), dur = 350;
    cancelAnimationFrame(raf.current);
    const step = (t: number) => {
      // Clamp both ends: rAF/perf-clock skew (sleep, virtual time) must
      // never extrapolate a telemetry value outside [from, to].
      const p = Math.min(1, Math.max(0, (t - t0) / dur));
      const e = 1 - Math.pow(1 - p, 3);
      setShown(from + (to - from) * e);
      if (p < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, tween]);

  return <span className="num">{fmtValue(shown, kind, prefs, decimals)}</span>;
}

// ── Provenance: hover/tap reveals source, freshness, derivation ─────
export function SensorValue({ sensor, decimals = 1 }: { sensor: SensorPoint; decimals?: number }) {
  const prefs = usePrefs();
  const [open, setOpen] = useState(false);
  const stale = isStale(sensor);

  return (
    <span style={{ position: "relative", display: "inline-block" }}>
      <button
        className={stale ? "stale-value" : undefined}
        style={{ font: "inherit", minHeight: "unset", padding: 0, borderBottom: "1px dotted var(--ink-3)" }}
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        aria-label={`${sensor.metric} value, tap for source details`}
      >
        {stale
          ? <span className="num">{fmtValue(sensor.value, sensor.kind, prefs, decimals)}</span>
          : <TweenNumber value={sensor.value} kind={sensor.kind} decimals={decimals} />}
        <span style={{ color: "var(--ink-3)", fontSize: "0.85em", marginLeft: 3 }}>{unitLabel(sensor.kind, prefs)}</span>
        {stale && <span className="pill stale" style={{ marginLeft: 6 }}><span className="glyph">◌</span>STALE</span>}
      </button>
      {open && (
        <div className="popover" style={{ top: "calc(100% + 6px)", left: 0 }}>
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", fontSize: "var(--text-xs)" }}>
            <span style={{ color: "var(--ink-3)" }}>Source</span><span>{sensor.device}</span>
            <span style={{ color: "var(--ink-3)" }}>Metric</span><span className="num">{sensor.metric}</span>
            <span style={{ color: "var(--ink-3)" }}>Updated</span>
            <span className={stale ? "stale-value" : undefined}>{ago(sensor.lastUpdate)}{stale && " — treat as unverified"}</span>
            <span style={{ color: "var(--ink-3)" }}>Type</span><span>{sensor.provenance}</span>
          </div>
        </div>
      )}
    </span>
  );
}

// ── Repair clock: always visible where the asset appears ────────────
export function RepairClock({ deadline, compact = false }: { deadline: number; compact?: boolean }) {
  const d = daysLeft(deadline);
  const overdue = d < 0;
  const urgent = d <= 7;
  const level = overdue || urgent ? "critical" : "warning";
  const label = overdue
    ? `REPAIR OVERDUE ${-d}d`
    : compact ? `${d}d left` : `Repair window: ${d} days left`;
  return (
    <span
      className={`pill ${level}`}
      style={overdue ? { background: "var(--status-critical)", color: "#fff" } : undefined}
      role="status" aria-label={label}
    >
      <span className="glyph" aria-hidden>⏱</span>{label}
    </span>
  );
}

// ── Empty state = the tutorial ───────────────────────────────────────
export function EmptyState({ title, body, action, onAction }: {
  title: string; body: string; action?: string; onAction?: () => void;
}) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p>{body}</p>
      {action && <button className="btn primary" onClick={onAction}>{action}</button>}
    </div>
  );
}

// ── Contextual explainer: techs are not lawyers ──────────────────────
export function HelpTip({ term, children }: { term: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: "relative" }}>
      <button
        aria-label={`What is ${term}?`}
        onClick={() => setOpen((o) => !o)}
        style={{
          minHeight: "unset", width: 18, height: 18, borderRadius: "50%",
          border: "1px solid var(--line-2)", color: "var(--ink-3)",
          fontSize: 11, lineHeight: 1, marginLeft: 6, verticalAlign: "middle",
        }}
      >?</button>
      {open && (
        <>
          <div className="scrim" style={{ background: "transparent" }} onClick={() => setOpen(false)} />
          <div className="popover" style={{ top: "calc(100% + 6px)", left: -8 }}>
            <strong style={{ display: "block", marginBottom: 4 }}>{term}</strong>
            <span style={{ color: "var(--ink-2)" }}>{children}</span>
          </div>
        </>
      )}
    </span>
  );
}

// ── "What can I do here?" ────────────────────────────────────────────
export function ScreenGuide({ items }: { items: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button className="btn ghost sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        ？ What can I do here?
      </button>
      {open && (
        <>
          <div className="scrim" style={{ background: "transparent" }} onClick={() => setOpen(false)} />
          <div className="popover" style={{ top: "calc(100% + 6px)", right: 0, left: "auto", minWidth: 300 }}>
            <ul style={{ listStyle: "none", display: "grid", gap: 8 }}>
              {items.map((it) => (
                <li key={it} style={{ paddingLeft: 18, position: "relative" }}>
                  <span style={{ position: "absolute", left: 0, color: "var(--accent)" }}>›</span>{it}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

// ── Stat tile ────────────────────────────────────────────────────────
export function StatTile({ label, value, sub, level }: {
  label: string; value: ReactNode; sub?: ReactNode; level?: "critical" | "warning" | "ok";
}) {
  return (
    <div className={`panel${level === "critical" ? " stat-critical" : ""}`}
      style={{
        padding: "var(--space-4)",
        borderColor: level === "critical" ? "var(--status-critical)" : level === "warning" ? "var(--status-warning)" : undefined,
        borderLeftWidth: level ? 3 : undefined,
      }}>
      <div style={{ fontSize: "var(--text-xs)", fontWeight: 650, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 600, lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-2)", marginTop: 6 }}>{sub}</div>}
    </div>
  );
}
