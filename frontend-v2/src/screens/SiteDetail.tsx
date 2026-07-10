/**
 * Site detail — rooms, racks, assets.
 * Command mode: schematic tile view with live flow states.
 * Field mode: nested table, same data, faster to scan with gloves.
 */
import { useParams, useNavigate, NavLink } from "react-router-dom";
import { sites, rooms, assets, sensors, alarms, leakEvents, isStale } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { RepairClock, ScreenGuide, SensorValue, StatusPill } from "../components/core";
import { usePrefs } from "../state/prefs";
import { fmtValue } from "../lib/format";

export function SiteDetail() {
  useLiveTick();
  const prefs = usePrefs();
  const nav = useNavigate();
  const { siteId } = useParams();
  const site = sites.find((s) => s.id === siteId);

  if (!site) return <div className="empty"><h3>Site not found</h3><button className="btn primary" onClick={() => nav("/")}>Fleet overview</button></div>;

  const siteRooms = rooms.filter((r) => r.siteId === site.id);
  const openLeak = leakEvents.find((l) => l.siteId === site.id && l.stage !== "closed");

  const assetTile = (a: (typeof assets)[number]) => {
    const aSensors = sensors.filter((s) => s.assetId === a.id);
    const primary = aSensors[0];
    const alarm = alarms.find((x) => x.assetId === a.id && x.state === "active");
    const anyStale = aSensors.some((s) => isStale(s));
    const leak = leakEvents.find((l) => l.circuitId === a.circuitId && l.stage !== "closed");
    return { aSensors, primary, alarm, anyStale, leak };
  };

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <nav aria-label="Breadcrumb" style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>
        <NavLink to="/" style={{ color: "inherit" }}>Fleet</NavLink> › {site.name}
      </nav>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <div>
          <h1 style={{ fontSize: 24 }}>{site.name}</h1>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--ink-2)" }}>{site.city} · {site.kind === "grocery" ? "Grocery" : "Cold storage"}</div>
        </div>
        <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
          {openLeak && <RepairClock deadline={openLeak.repairDeadline} />}
          <ScreenGuide items={[
            "Rooms group the assets that share an environment and a target temperature",
            prefs.mode === "command"
              ? "Tiles glow with live state: running compressors breathe, defrosts advance"
              : "Field mode shows the same assets as a table — faster with gloves",
            "Click any asset for live charts, setpoints, and service history",
          ]} />
        </div>
      </div>

      {siteRooms.map((room) => {
        const roomAssets = assets.filter((a) => a.roomId === room.id);
        return (
          <section key={room.id} aria-label={room.name}>
            <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-3)", marginBottom: "var(--space-3)" }}>
              <h2 style={{ fontSize: 17 }}>{room.name}</h2>
              <span style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }} className="num">
                target {fmtValue(room.targetF, "temp", prefs, 0)}°{prefs.tempUnit}
              </span>
            </div>

            {prefs.mode === "command" ? (
              /* ── Schematic tiles ── */
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: "var(--space-3)" }}>
                {roomAssets.map((a) => {
                  const { primary, alarm, anyStale, leak } = assetTile(a);
                  return (
                    <button key={a.id} className={`panel-2 rise${anyStale ? " stale-wash" : ""}`}
                      onClick={() => nav(`/assets/${a.id}`)}
                      style={{
                        padding: "var(--space-4)", textAlign: "left", display: "grid", gap: 8,
                        borderColor: alarm?.severity === "critical" ? "var(--status-critical)" : undefined,
                        cursor: "pointer",
                      }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{a.name}</span>
                        {a.running && <span className="breathe" aria-label="running" style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--status-ok)" }} />}
                      </div>
                      {primary && <div style={{ fontSize: 21 }}><SensorValue sensor={primary} /></div>}
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {alarm && <StatusPill level={alarm.severity === "info" ? "info" : alarm.severity} label={alarm.severity} />}
                        {a.inDefrost && <span className="pill info"><span className="glyph">❄</span>{Math.round(a.defrostProgress * 100)}%</span>}
                        {leak && <RepairClock deadline={leak.repairDeadline} compact />}
                        {!alarm && !a.inDefrost && !leak && <StatusPill level={a.running ? "ok" : "stale"} label={a.running ? "running" : "stopped"} />}
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              /* ── Field: nested table ── */
              <div className="panel" style={{ overflow: "hidden" }}>
                <table className="table">
                  <thead><tr><th>Asset</th><th>State</th><th>Primary reading</th><th>Status</th></tr></thead>
                  <tbody>
                    {roomAssets.map((a) => {
                      const { primary, alarm, leak } = assetTile(a);
                      return (
                        <tr key={a.id} className="clickable" onClick={() => nav(`/assets/${a.id}`)}>
                          <td style={{ fontWeight: 600 }}>{a.name}</td>
                          <td>{a.inDefrost
                            ? <span className="pill info"><span className="glyph">❄</span>DEFROST {Math.round(a.defrostProgress * 100)}%</span>
                            : <StatusPill level={a.running ? "ok" : "stale"} label={a.running ? "RUNNING" : "STOPPED"} />}</td>
                          <td>{primary ? <SensorValue sensor={primary} /> : "—"}</td>
                          <td style={{ display: "flex", gap: 6, alignItems: "center", height: "var(--row-h)" }}>
                            {alarm && <StatusPill level={alarm.severity === "info" ? "info" : alarm.severity} label={alarm.title.slice(0, 28)} />}
                            {leak && <RepairClock deadline={leak.repairDeadline} compact />}
                            {!alarm && !leak && <span style={{ color: "var(--ink-3)", fontSize: "var(--text-xs)" }}>OK</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
