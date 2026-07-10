/** Edge agent health — where techs live during install. */
import { agents, sites } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { ScreenGuide, StatusPill } from "../components/core";
import { ago } from "../lib/format";

export function Agents() {
  useLiveTick();
  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <h1 style={{ fontSize: 24 }}>Edge agents</h1>
        <div style={{ display: "flex", gap: "var(--space-3)" }}>
          <button className="btn primary">Add agent</button>
          <ScreenGuide items={[
            "Each site runs a small gateway that reads controllers over BACnet/Modbus",
            "A stale agent means every sensor at that site is unverified — fix this first",
            "Discovered vs mapped shows install progress: unmapped points aren't monitored yet",
            "Agents buffer locally during outages and back-fill when reconnected",
          ]} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "var(--space-4)" }}>
        {agents.map((a) => {
          const site = sites.find((s) => s.id === a.siteId);
          const mappingPct = Math.round((a.mappedPoints / a.discoveredPoints) * 100);
          const stale = a.state !== "connected";
          return (
            <div key={a.id} className={`panel${stale ? "" : ""}`} style={{ padding: "var(--space-4)", borderColor: stale ? "var(--status-warning)" : undefined, borderLeftWidth: stale ? 3 : undefined }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-3)" }}>
                <div>
                  <div style={{ fontWeight: 650 }} className="num">{a.name}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>{site?.name}</div>
                </div>
                {a.state === "connected"
                  ? <StatusPill level="ok" label="Connected" />
                  : <StatusPill level="warning" label={`Stale · ${ago(a.lastCheckin)}`} />}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 14px", fontSize: "var(--text-sm)" }}>
                <span style={{ color: "var(--ink-3)" }}>Last check-in</span>
                <span className="num" style={{ color: stale ? "var(--status-warning)" : undefined }}>{ago(a.lastCheckin)}</span>
                <span style={{ color: "var(--ink-3)" }}>Version</span><span className="num">{a.version}</span>
                <span style={{ color: "var(--ink-3)" }}>Points</span>
                <span className="num">{a.mappedPoints}/{a.discoveredPoints} mapped</span>
              </div>
              <div style={{ marginTop: "var(--space-3)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--text-xs)", color: "var(--ink-3)", marginBottom: 4 }}>
                  <span>Mapping progress</span><span className="num">{mappingPct}%</span>
                </div>
                <div style={{ height: 6, background: "var(--surface-0)", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${mappingPct}%`, background: mappingPct === 100 ? "var(--status-ok)" : "var(--accent)" }} />
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: "var(--space-3)" }}>
                <button className="btn sm">Scan network</button>
                <button className="btn sm ghost">View mapping</button>
                <button className="btn sm ghost">Logs</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
