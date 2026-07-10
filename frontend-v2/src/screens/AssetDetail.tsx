/**
 * Asset detail — live telemetry with brush-zoom charts, setpoints,
 * runtime, and the repair clock if this asset's circuit has an open leak.
 * A compressor tile breathes when running (full motion only).
 */
import { useParams, useNavigate, NavLink } from "react-router-dom";
import { assets, sensors, sites, leakEvents, seriesFor, isStale } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { LiveChart } from "../components/LiveChart";
import { RepairClock, ScreenGuide, SensorValue, StatusPill } from "../components/core";
import { usePrefs } from "../state/prefs";
import { ago, fmtValue } from "../lib/format";

export function AssetDetail() {
  useLiveTick();
  const prefs = usePrefs();
  const nav = useNavigate();
  const { assetId } = useParams();
  const asset = assets.find((a) => a.id === assetId);

  if (!asset) {
    return <div className="empty"><h3>Asset not found</h3><p>It may have been decommissioned. Head back to the fleet view.</p><button className="btn primary" onClick={() => nav("/")}>Fleet overview</button></div>;
  }

  const site = sites.find((s) => s.id === asset.siteId)!;
  const assetSensors = sensors.filter((s) => s.assetId === asset.id);
  const openLeak = leakEvents.find((l) => l.circuitId === asset.circuitId && l.stage !== "closed");

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <nav aria-label="Breadcrumb" style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>
        <NavLink to="/" style={{ color: "inherit" }}>Fleet</NavLink> ›{" "}
        <NavLink to={`/sites/${site.id}`} style={{ color: "inherit" }}>{site.name}</NavLink> › {asset.name}
      </nav>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <h1 style={{ fontSize: 24 }}>{asset.name}</h1>
          {asset.running
            ? <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span className="breathe" aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--status-ok)" }} />
                <StatusPill level="ok" label="Running" />
              </span>
            : <StatusPill level="stale" label="Stopped" />}
          {asset.inDefrost && (
            <span className="pill info" role="status">
              <span className="glyph">❄</span>
              DEFROST {Math.round(asset.defrostProgress * 100)}%
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
          {openLeak && <RepairClock deadline={openLeak.repairDeadline} />}
          <ScreenGuide items={[
            "Every number is tappable — see its source device, freshness, and whether it's raw or derived",
            "Drag on a chart to zoom, double-click to reset and resume live tailing",
            "Setpoint changes queue a command to the edge agent with a full audit trail",
            "If this asset's circuit has an open leak event, the repair clock shows here",
          ]} />
        </div>
      </div>

      {/* Defrost progress bar — visibly advances */}
      {asset.inDefrost && (
        <div className="panel" style={{ padding: "var(--space-3) var(--space-4)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--text-xs)", color: "var(--ink-2)", marginBottom: 6 }}>
            <span>Defrost cycle in progress</span>
            <span className="num">{Math.round(asset.defrostProgress * 100)}%</span>
          </div>
          <div style={{ height: 6, background: "var(--surface-0)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${asset.defrostProgress * 100}%`, background: "var(--status-info)", transition: "width var(--dur-slow) linear" }} />
          </div>
        </div>
      )}

      {/* Snapshot row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "var(--space-3)" }}>
        {assetSensors.map((s) => (
          <div key={s.id} className={`panel${isStale(s) ? " stale-wash" : ""}`} style={{ padding: "var(--space-3) var(--space-4)" }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 650, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-3)", marginBottom: 4 }}>
              {s.metric.replace(/_/g, " ")}
            </div>
            <div style={{ fontSize: 22 }}><SensorValue sensor={s} /></div>
            <div style={{ fontSize: "var(--text-xs)", color: isStale(s) ? "var(--status-stale)" : "var(--ink-3)", marginTop: 2 }}>
              {isStale(s) ? `last report ${ago(s.lastUpdate)}` : ago(s.lastUpdate)}
            </div>
          </div>
        ))}
        <div className="panel" style={{ padding: "var(--space-3) var(--space-4)" }}>
          <div style={{ fontSize: "var(--text-xs)", fontWeight: 650, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-3)", marginBottom: 4 }}>Runtime / cycles</div>
          <div style={{ fontSize: 22 }} className="num">{asset.runtimeHours.toLocaleString()}h</div>
          <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)", marginTop: 2 }} className="num">{asset.cyclesToday} starts today</div>
        </div>
        {asset.setpoint && (
          <div className="panel" style={{ padding: "var(--space-3) var(--space-4)", borderColor: "var(--accent-line)" }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 650, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-3)", marginBottom: 4 }}>
              {asset.setpoint.label} setpoint
            </div>
            <div style={{ fontSize: 22 }} className="num">
              {fmtValue(asset.setpoint.value, asset.setpoint.kind, prefs, 0)}
              <span style={{ fontSize: 13, color: "var(--ink-3)" }}> {asset.setpoint.kind === "temp" ? `°${prefs.tempUnit}` : prefs.pressureUnit}</span>
            </div>
            <button className="btn sm" style={{ marginTop: 6 }}>Adjust…</button>
          </div>
        )}
      </div>

      {/* Live charts with brush + zoom */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: "var(--space-4)" }}>
        {assetSensors.slice(0, 4).map((s) => (
          <div key={s.id} className="panel" style={{ padding: "var(--space-4)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--space-2)" }}>
              <span style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>{s.metric.replace(/_/g, " ")}</span>
              {isStale(s)
                ? <StatusPill level="stale" label={`stale · ${ago(s.lastUpdate)}`} />
                : <span style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }} className="num">live · 2s</span>}
            </div>
            <LiveChart series={seriesFor(s.id)} kind={s.kind} label={s.metric} stale={isStale(s)} />
          </div>
        ))}
      </div>

      {/* Service history */}
      <div className="panel" style={{ overflow: "hidden" }}>
        <div style={{ padding: "var(--space-3) var(--space-4)", fontSize: "var(--text-xs)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", borderBottom: "1px solid var(--line-1)" }}>Service history</div>
        <table className="table">
          <thead><tr><th>Date</th><th>Work</th><th>Technician</th><th>Outcome</th></tr></thead>
          <tbody>
            <tr><td className="num" style={{ fontSize: "var(--text-xs)" }}>Jun 12</td><td>Oil change + vibration check</td><td>P. Doe · CoolServ</td><td><StatusPill level="ok" label="Completed" /></td></tr>
            <tr><td className="num" style={{ fontSize: "var(--text-xs)" }}>Mar 03</td><td>Suction valve replacement</td><td>P. Doe · CoolServ</td><td><StatusPill level="ok" label="Verified leak-free" /></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
