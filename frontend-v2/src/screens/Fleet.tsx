/**
 * Fleet overview — answers "am I okay?" in under two seconds.
 * Rollup tiles up top (critical states render instantly), then per-site
 * health with alarm counts, leak clocks, refrigerant exposure.
 */
import { useNavigate } from "react-router-dom";
import { usePrefs } from "../state/prefs";
import { useLiveTick } from "../mock/useLive";
import { sites, assets, alarms, leakEvents, circuits, agents, sensors, isStale } from "../mock/engine";
import { RepairClock, ScreenGuide, StatTile, StatusPill } from "../components/core";
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
  const worstLeakRate = Math.max(...circuits.map((c) => c.fullChargeLbs ? (c.addedLbs365 / c.fullChargeLbs) * 100 : 0));

  return (
    <div style={{ display: "grid", gap: "var(--space-5)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-3)" }}>
        <h1 style={{ fontSize: 24 }}>Fleet</h1>
        <ScreenGuide items={[
          "See every site's health, alarms, and compliance exposure at a glance",
          "Click a site row to open rooms, racks, and assets",
          "Click any tile to jump to the detail behind the number",
          "Press M to switch Field/Command mode, ⌘K to search anything",
        ]} />
      </div>

      {/* ── Rollup: the two-second answer ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: "var(--space-4)" }}>
        <div onClick={() => nav("/alarms")} style={{ cursor: "pointer" }}>
          <StatTile
            label="Critical alarms"
            level={critical.length ? "critical" : "ok"}
            value={<span className="num">{critical.length}</span>}
            sub={critical.length ? critical[0].title : "No critical alarms"}
          />
        </div>
        <div onClick={() => nav("/alarms")} style={{ cursor: "pointer" }}>
          <StatTile
            label="Open alarms"
            level={activeAlarms.length ? "warning" : "ok"}
            value={<span className="num">{activeAlarms.length}</span>}
            sub={`${alarms.filter((a) => a.state === "acknowledged").length} acknowledged`}
          />
        </div>
        <div onClick={() => nav("/leaks")} style={{ cursor: "pointer" }}>
          <StatTile
            label="Open leak events"
            level={openLeaks.length ? "critical" : "ok"}
            value={<span className="num">{openLeaks.length}</span>}
            sub={openLeaks.length ? <RepairClock deadline={openLeaks[0].repairDeadline} compact /> : "All circuits within threshold"}
          />
        </div>
        <div onClick={() => nav("/ledger")} style={{ cursor: "pointer" }}>
          <StatTile
            label="Refrigerant on system"
            value={<><span className="num">{fmtValue(totalCharge, "mass", prefs, 0)}</span><span style={{ fontSize: 15, color: "var(--ink-3)" }} > {prefs.massUnit}</span></>}
            sub={`Worst circuit leak rate ${worstLeakRate.toFixed(1)}% (threshold 20%)`}
          />
        </div>
        <div onClick={() => nav("/agents")} style={{ cursor: "pointer" }}>
          <StatTile
            label="Sensors reporting"
            level={staleCount ? "warning" : "ok"}
            value={<span className="num">{sensors.length - staleCount}/{sensors.length}</span>}
            sub={staleCount ? `${staleCount} stale — values unverified` : "All fresh"}
          />
        </div>
      </div>

      {/* ── Per-site table ── */}
      <div className="panel" style={{ overflow: "hidden" }}>
        <table className="table">
          <thead>
            <tr>
              <th>Site</th>
              <th>Health</th>
              <th className="num">Assets</th>
              <th className="num">Alarms</th>
              <th>Leak events</th>
              <th>Agent</th>
              <th className="num">Charge ({prefs.massUnit})</th>
            </tr>
          </thead>
          <tbody>
            {sites.map((s) => {
              const siteAssets = assets.filter((a) => a.siteId === s.id);
              const siteAlarms = alarms.filter((a) => a.siteId === s.id && a.state === "active");
              const siteCritical = siteAlarms.some((a) => a.severity === "critical");
              const siteLeaks = leakEvents.filter((l) => l.siteId === s.id && l.stage !== "closed");
              const agent = agents.find((a) => a.siteId === s.id);
              const charge = circuits.filter((c) => c.siteId === s.id).reduce((x, c) => x + c.fullChargeLbs, 0);
              return (
                <tr key={s.id} className="clickable" onClick={() => nav(`/sites/${s.id}`)}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{s.name}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>{s.city} · {s.kind === "grocery" ? "Grocery" : "Cold storage"}</div>
                  </td>
                  <td>
                    {siteCritical
                      ? <StatusPill level="critical" label="Critical" />
                      : siteAlarms.length || siteLeaks.length
                        ? <StatusPill level="warning" label="Attention" />
                        : <StatusPill level="ok" label="Healthy" />}
                  </td>
                  <td className="num">{siteAssets.length}</td>
                  <td className="num">{siteAlarms.length}</td>
                  <td>{siteLeaks.length
                    ? <RepairClock deadline={siteLeaks[0].repairDeadline} compact />
                    : <span style={{ color: "var(--ink-3)" }}>none</span>}</td>
                  <td>
                    {agent?.state === "connected"
                      ? <StatusPill level="ok" label="Online" />
                      : <StatusPill level="stale" label="Stale" />}
                  </td>
                  <td className="num">{fmtValue(charge, "mass", prefs, 0)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
