/**
 * Leak events — the compliance heart.
 * Detection → verification → repair → re-verification → close, with the
 * 30-day repair clock unmissable and "what's missing to close" explicit.
 */
import { useNavigate } from "react-router-dom";
import { leakEvents, circuits, sites } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { EmptyState, HelpTip, RepairClock, ScreenGuide, StatusPill } from "../components/core";
import { usePrefs } from "../state/prefs";
import { fmtTime, fmtValue, tzBadge } from "../lib/format";
import type { LeakStage } from "../mock/types";

const STAGES: Array<{ key: LeakStage; label: string }> = [
  { key: "detection", label: "Detection" },
  { key: "verification", label: "Initial verification" },
  { key: "repair", label: "Repair" },
  { key: "reverification", label: "Follow-up verification" },
  { key: "closed", label: "Closed" },
];

function StageTrack({ done, current }: { done: Partial<Record<LeakStage, number>>; current: LeakStage }) {
  const currentIdx = STAGES.findIndex((s) => s.key === current);
  return (
    <ol style={{ display: "flex", listStyle: "none", gap: 0, alignItems: "center", flexWrap: "wrap" }}>
      {STAGES.map((s, i) => {
        const isDone = done[s.key] != null;
        const isCurrent = i === currentIdx && !isDone;
        return (
          <li key={s.key} style={{ display: "flex", alignItems: "center" }}>
            <span
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                fontSize: "var(--text-xs)", fontWeight: 650,
                color: isDone ? "var(--status-ok)" : isCurrent ? "var(--ink-1)" : "var(--ink-3)",
              }}
            >
              <span aria-hidden style={{
                width: 18, height: 18, borderRadius: "50%", display: "inline-flex",
                alignItems: "center", justifyContent: "center", fontSize: 10,
                border: `2px solid ${isDone ? "var(--status-ok)" : isCurrent ? "var(--accent)" : "var(--line-2)"}`,
                background: isDone ? "var(--status-ok-bg)" : isCurrent ? "var(--accent-soft)" : "transparent",
              }}>{isDone ? "✓" : i + 1}</span>
              {s.label}
            </span>
            {i < STAGES.length - 1 && (
              <span aria-hidden style={{ width: 26, height: 2, margin: "0 6px", background: isDone ? "var(--status-ok)" : "var(--line-2)" }} />
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function Leaks() {
  useLiveTick();
  const prefs = usePrefs();
  const nav = useNavigate();
  const open = leakEvents.filter((l) => l.stage !== "closed");
  const closed = leakEvents.filter((l) => l.stage === "closed");

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <h1 style={{ fontSize: 24 }}>
          Leak events
          <HelpTip term="Leak event">
            A detected refrigerant loss on a circuit. Under the AIM Act Leak Repair Rule, crossing a
            20% annual leak rate starts a 30-day repair clock with verification tests before and after.
          </HelpTip>
        </h1>
        <ScreenGuide items={[
          "Each event walks detection → verification → repair → re-verification → close",
          "The repair clock counts down the 30-day AIM Act window from detection",
          "'Missing to close' lists exactly what documentation is still required",
          "Closed events are immutable — corrections create new versions with an audit trail",
        ]} />
      </div>

      {open.length === 0 ? (
        <EmptyState
          title="No open leak events"
          body="When automated detection (or a technician) confirms refrigerant loss on a circuit, the event appears here with its regulatory clock and required steps. That's a good empty state to have."
          action="See how detection works"
          onAction={() => nav("/agents")}
        />
      ) : (
        open.map((l) => {
          const circuit = circuits.find((c) => c.id === l.circuitId);
          const site = sites.find((s) => s.id === l.siteId);
          const leakRate = circuit ? (circuit.addedLbs365 / circuit.fullChargeLbs) * 100 : 0;
          return (
            <section key={l.id} className="panel" style={{ padding: "var(--space-5)", borderLeft: "4px solid var(--status-critical)" }} aria-label={`Open leak event on ${l.circuitName}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
                <div>
                  <h2 style={{ fontSize: 19 }}>{l.circuitName} <span style={{ color: "var(--ink-3)", fontWeight: 400, fontSize: "var(--text-sm)" }}>· {site?.name}</span></h2>
                  <div style={{ display: "flex", gap: "var(--space-4)", marginTop: 6, fontSize: "var(--text-sm)", color: "var(--ink-2)", flexWrap: "wrap" }}>
                    <span>Detected {fmtTime(l.detectedAt, prefs, site?.tz ?? "America/Chicago")} <span style={{ color: "var(--ink-3)" }}>({tzBadge(prefs, site?.tz ?? "America/Chicago")})</span></span>
                    <span className="num">{fmtValue(l.lbsLost, "mass", prefs, 0)} {prefs.massUnit} lost</span>
                    <span>
                      Annual leak rate <strong className="num" style={{ color: leakRate >= 20 ? "var(--status-critical)" : "var(--ink-1)" }}>{leakRate.toFixed(1)}%</strong>
                      <HelpTip term="Annual leak rate">
                        Refrigerant added over the trailing 365 days divided by the circuit's full charge.
                        At or above 20% (commercial refrigeration), the EPA requires repair within 30 days.
                      </HelpTip>
                    </span>
                  </div>
                </div>
                <RepairClock deadline={l.repairDeadline} />
              </div>

              <StageTrack done={l.stagesDone} current={l.stage} />

              {l.missingToClose.length > 0 && (
                <div style={{ marginTop: "var(--space-4)", padding: "var(--space-3)", background: "var(--status-warning-bg)", border: "1px solid var(--status-warning)", borderRadius: "var(--radius-sm)" }}>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                    Missing to close
                  </div>
                  <ul style={{ listStyle: "none", display: "grid", gap: 4, fontSize: "var(--text-sm)" }}>
                    {l.missingToClose.map((m) => (
                      <li key={m} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span aria-hidden style={{ color: "var(--status-warning)" }}>☐</span>{m}
                      </li>
                    ))}
                  </ul>
                  <div style={{ display: "flex", gap: 8, marginTop: "var(--space-3)" }}>
                    <button className="btn primary sm">Log repair record</button>
                    <button className="btn sm">Record verification test</button>
                  </div>
                </div>
              )}
            </section>
          );
        })
      )}

      {closed.length > 0 && (
        <div className="panel" style={{ overflow: "hidden" }}>
          <div style={{ padding: "var(--space-3) var(--space-4)", fontSize: "var(--text-xs)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", borderBottom: "1px solid var(--line-1)" }}>
            Closed events (immutable record)
          </div>
          <table className="table">
            <thead><tr><th>Circuit</th><th>Site</th><th>Detected</th><th>Closed</th><th className="num">Lost ({prefs.massUnit})</th><th>Outcome</th></tr></thead>
            <tbody>
              {closed.map((l) => {
                const site = sites.find((s) => s.id === l.siteId);
                return (
                  <tr key={l.id}>
                    <td style={{ fontWeight: 600 }}>{l.circuitName}</td>
                    <td>{site?.name}</td>
                    <td className="num" style={{ fontSize: "var(--text-xs)" }}>{fmtTime(l.detectedAt, prefs, site?.tz ?? "UTC")}</td>
                    <td className="num" style={{ fontSize: "var(--text-xs)" }}>{l.stagesDone.closed ? fmtTime(l.stagesDone.closed, prefs, site?.tz ?? "UTC") : "—"}</td>
                    <td className="num">{fmtValue(l.lbsLost, "mass", prefs, 0)}</td>
                    <td><StatusPill level="ok" label="Repaired & verified" /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
