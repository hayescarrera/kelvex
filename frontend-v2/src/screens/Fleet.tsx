/**
 * Dashboard — the single pane of glass, Axiom-style:
 * KPI cards with period deltas, a ranked "Needs attention" queue
 * (highest risk floats to the top), per-site health scores, and the
 * compressor fleet ranked by failure probability.
 */
import { useNavigate } from "react-router-dom";
import { usePrefs } from "../state/prefs";
import { useLiveTick } from "../mock/useLive";
import {
  sites, assets, alarms, leakEvents, circuits, agents, sensors,
  isStale, siteHealth, needsAttention, rankedCompressors,
} from "../mock/engine";
import { Delta, HealthRing, RepairClock, ScreenGuide, StatusPill } from "../components/core";
import { fmtValue } from "../lib/format";

export function Fleet() {
  useLiveTick();
  const prefs = usePrefs();
  const nav = useNavigate();

  const activeAlarms = alarms.filter((a) => a.state === "active");
  const critical = activeAlarms.filter((a) => a.severity === "critical");
  const openLeaks = leakEvents.filter((l) => l.stage !== "closed");
  const staleCount = sensors.filter((s) => isStale(s)).length;
  const totalCharge = circuits.reduce((sum, c) => sum + c.fullChargeLbs, 0);
  const attention = needsAttention();
  const compressors = rankedCompressors();

  interface Kpi {
    label: string; value: string; delta: React.ReactNode; sub: string;
    href: string; level?: "critical" | "warning";
  }
  const kpis: Kpi[] = [
    { label: "Open alarms", value: String(activeAlarms.length), delta: <Delta value={-2} goodWhenDown suffix="" />, sub: `${critical.length} critical`, href: "/alarms", level: critical.length ? "critical" : undefined },
    { label: "Open leak events", value: String(openLeaks.length), delta: <Delta value={0} suffix="" />, sub: openLeaks.length ? "repair clock running" : "none open", href: "/leaks", level: openLeaks.length ? "warning" : undefined },
    { label: "Sensors reporting", value: `${sensors.length - staleCount}/${sensors.length}`, delta: <Delta value={staleCount ? -3 : 0} goodWhenDown={false} suffix="%" />, sub: staleCount ? `${staleCount} stale` : "all fresh", href: "/agents" },
    { label: `Refrigerant (${prefs.massUnit})`, value: fmtValue(totalCharge, "mass", prefs, 0), delta: <Delta value={-4.2} goodWhenDown />, sub: "loss rate vs last quarter", href: "/ledger" },
    { label: "Energy (7d)", value: "41.2 MWh", delta: <Delta value={-6.8} goodWhenDown />, sub: "vs prior 7 days", href: "/compliance" },
  ];

  return (
    <div style={{ display: "grid", gap: "var(--space-5)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-3)" }}>
        <div>
          <h1 style={{ fontSize: 22 }}>Dashboard</h1>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--ink-2)" }}>All sites · updated live</div>
        </div>
        <ScreenGuide items={[
          "KPI cards show the fleet right now, with movement vs the prior period",
          "'Needs attention' ranks everything urgent — work top to bottom",
          "Site cards carry a 0–100 health score; click through for rooms and racks",
          "Compressors are ranked by failure probability — highest risk first",
        ]} />
      </div>

      {/* ── KPI cards ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(185px, 1fr))", gap: "var(--space-4)" }}>
        {kpis.map((k) => (
          <button key={k.label} className="panel" onClick={() => nav(k.href)}
            style={{
              padding: "var(--space-4)", textAlign: "left", cursor: "pointer",
              borderTop: k.level === "critical" ? "3px solid var(--status-critical)" : k.level === "warning" ? "3px solid var(--status-warning)" : undefined,
            }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 650, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", marginBottom: 8 }}>{k.label}</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <span style={{ fontFamily: "var(--font-display)", fontSize: 26, fontWeight: 600 }} className="num">{k.value}</span>
              {k.delta}
            </div>
            <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)", marginTop: 6 }}>{k.sub}</div>
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(380px, 5fr) minmax(320px, 4fr)", gap: "var(--space-4)", alignItems: "start" }}>
        {/* ── Needs attention (ranked) ── */}
        <section className="panel" aria-label="Needs attention">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "var(--space-3) var(--space-4)", borderBottom: "1px solid var(--line-1)" }}>
            <h2 style={{ fontSize: 15 }}>Needs attention</h2>
            <span style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>ranked by urgency</span>
          </div>
          {attention.length === 0 ? (
            <div style={{ padding: "var(--space-5)", color: "var(--ink-2)", fontSize: "var(--text-sm)" }}>
              Nothing needs you right now. New alarms, repair deadlines, and rising failure risk land here, most urgent first.
            </div>
          ) : (
            <ol style={{ listStyle: "none" }}>
              {attention.map((it, i) => {
                const site = sites.find((s) => s.id === it.siteId);
                const kindPill =
                  it.kind === "alarm" ? <StatusPill level="critical" label="alarm" /> :
                  it.kind === "leak" ? <StatusPill level="warning" label="leak" /> :
                  it.kind === "compressor" ? <StatusPill level="warning" label="risk" /> :
                  <StatusPill level="stale" label="stale" />;
                return (
                  <li key={it.id}>
                    <button onClick={() => nav(it.href)} style={{
                      display: "flex", gap: "var(--space-3)", alignItems: "flex-start", width: "100%",
                      textAlign: "left", padding: "var(--space-3) var(--space-4)",
                      borderBottom: "1px solid var(--line-1)", cursor: "pointer",
                    }}>
                      <span className="num" style={{ color: "var(--ink-3)", fontSize: "var(--text-xs)", marginTop: 3, width: 16 }}>{i + 1}</span>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>{it.title}</div>
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-2)" }}>{it.detail}</div>
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)", marginTop: 2 }}>{site?.name}</div>
                      </div>
                      <span style={{ marginLeft: "auto", flexShrink: 0 }}>{kindPill}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </section>

        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {/* ── Site health ── */}
          <section className="panel" aria-label="Sites">
            <div style={{ padding: "var(--space-3) var(--space-4)", borderBottom: "1px solid var(--line-1)" }}>
              <h2 style={{ fontSize: 15 }}>Sites</h2>
            </div>
            {sites.map((s) => {
              const health = siteHealth(s.id);
              const siteLeak = leakEvents.find((l) => l.siteId === s.id && l.stage !== "closed");
              const agent = agents.find((a) => a.siteId === s.id);
              return (
                <button key={s.id} onClick={() => nav(`/sites/${s.id}`)} style={{
                  display: "flex", alignItems: "center", gap: "var(--space-4)", width: "100%",
                  padding: "var(--space-3) var(--space-4)", borderBottom: "1px solid var(--line-1)",
                  textAlign: "left", cursor: "pointer",
                }}>
                  <HealthRing score={health} size={46} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>{s.name}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>
                      {assets.filter((a) => a.siteId === s.id).length} assets · {s.kind === "grocery" ? "grocery" : "cold storage"}
                      {agent?.state !== "connected" && <span style={{ color: "var(--status-warning)" }}> · gateway stale</span>}
                    </div>
                  </div>
                  <span style={{ marginLeft: "auto", flexShrink: 0 }}>
                    {siteLeak && <RepairClock deadline={siteLeak.repairDeadline} compact />}
                  </span>
                </button>
              );
            })}
          </section>

          {/* ── Compressor risk ranking ── */}
          <section className="panel" aria-label="Compressors by failure risk">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "var(--space-3) var(--space-4)", borderBottom: "1px solid var(--line-1)" }}>
              <h2 style={{ fontSize: 15 }}>Compressors by failure risk</h2>
              <span style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>live health scoring</span>
            </div>
            {compressors.map(({ asset, prob }) => (
              <button key={asset.id} onClick={() => nav(`/assets/${asset.id}`)} style={{
                display: "flex", alignItems: "center", gap: "var(--space-3)", width: "100%",
                padding: "var(--space-2) var(--space-4)", minHeight: 44,
                borderBottom: "1px solid var(--line-1)", textAlign: "left", cursor: "pointer",
              }}>
                <div style={{ minWidth: 0, flexShrink: 0, width: 150 }}>
                  <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>{asset.name}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>{sites.find((s) => s.id === asset.siteId)?.name}</div>
                </div>
                <div style={{ flex: 1, height: 8, background: "var(--surface-0)", borderRadius: 4, overflow: "hidden" }}>
                  <div style={{
                    height: "100%", width: `${prob * 100}%`, borderRadius: 4,
                    background: prob >= 0.5 ? "var(--status-critical)" : prob >= 0.25 ? "var(--status-warning)" : "var(--status-ok)",
                  }} />
                </div>
                <span className="num" style={{
                  fontSize: "var(--text-sm)", fontWeight: 650, width: 42, textAlign: "right",
                  color: prob >= 0.5 ? "var(--status-critical)" : prob >= 0.25 ? "var(--status-warning)" : "var(--ink-2)",
                }}>{(prob * 100).toFixed(0)}%</span>
              </button>
            ))}
          </section>
        </div>
      </div>
    </div>
  );
}
