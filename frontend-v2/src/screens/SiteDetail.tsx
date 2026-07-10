/**
 * Site detail — rooms, racks, assets as live tile cards.
 */
import { useParams, useNavigate, NavLink } from "react-router-dom";
import { sites, rooms, assets, sensors, alarms, leakEvents, isStale, siteHealth } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { HealthRing, RepairClock, ScreenGuide, SensorValue, StatusPill } from "../components/core";
import { usePrefs } from "../state/prefs";
import { fmtValue } from "../lib/format";

export function SiteDetail() {
  useLiveTick();
  const prefs = usePrefs();
  const nav = useNavigate();
  const { siteId } = useParams();
  const site = sites.find((s) => s.id === siteId);

  if (!site) return <div className="empty"><h3>Site not found</h3><button className="btn primary" onClick={() => nav("/")}>Dashboard</button></div>;

  const siteRooms = rooms.filter((r) => r.siteId === site.id);
  const openLeak = leakEvents.find((l) => l.siteId === site.id && l.stage !== "closed");

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <nav aria-label="Breadcrumb" style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>
        <NavLink to="/" style={{ color: "inherit" }}>Dashboard</NavLink> › {site.name}
      </nav>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
          <HealthRing score={siteHealth(site.id)} size={56} />
          <div>
            <h1 style={{ fontSize: 22 }}>{site.name}</h1>
            <div style={{ fontSize: "var(--text-sm)", color: "var(--ink-2)" }}>{site.city} · {site.kind === "grocery" ? "Grocery" : "Cold storage"}</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
          {openLeak && <RepairClock deadline={openLeak.repairDeadline} />}
          <ScreenGuide items={[
            "The health score rolls up alarms, stale sensors, leak clocks, and gateway state",
            "Rooms group assets sharing an environment and target temperature",
            "Tiles carry live state: running dots, advancing defrosts, repair clocks",
            "Click any asset for live charts, setpoints, and service history",
          ]} />
        </div>
      </div>

      {siteRooms.map((room) => {
        const roomAssets = assets.filter((a) => a.roomId === room.id);
        return (
          <section key={room.id} aria-label={room.name}>
            <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-3)", marginBottom: "var(--space-3)" }}>
              <h2 style={{ fontSize: 16 }}>{room.name}</h2>
              <span style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }} className="num">
                target {fmtValue(room.targetF, "temp", prefs, 0)}°{prefs.tempUnit}
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: "var(--space-3)" }}>
              {roomAssets.map((a) => {
                const aSensors = sensors.filter((s) => s.assetId === a.id);
                const primary = aSensors[0];
                const alarm = alarms.find((x) => x.assetId === a.id && x.state === "active");
                const anyStale = aSensors.some((s) => isStale(s));
                const leak = leakEvents.find((l) => l.circuitId === a.circuitId && l.stage !== "closed");
                return (
                  <button key={a.id} className={`panel${anyStale ? " stale-wash" : ""}`}
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
                    {primary && <div style={{ fontSize: 20 }}><SensorValue sensor={primary} /></div>}
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
          </section>
        );
      })}
    </div>
  );
}
