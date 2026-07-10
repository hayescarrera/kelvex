/** Refrigerant ledger — charge by circuit, additions/recoveries, reconciliation. */
import { circuits, ledger, sites } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { HelpTip, ScreenGuide, StatusPill } from "../components/core";
import { usePrefs } from "../state/prefs";
import { fmtTime, fmtValue } from "../lib/format";

export function Ledger() {
  useLiveTick();
  const prefs = usePrefs();

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <h1 style={{ fontSize: 24 }}>Refrigerant ledger</h1>
        <div style={{ display: "flex", gap: "var(--space-3)" }}>
          <button className="btn primary">Log addition</button>
          <button className="btn">Log recovery</button>
          <ScreenGuide items={[
            "Every pound in or out of a circuit, with technician and EPA cert",
            "Additions feed the annual leak-rate calculation automatically",
            "Ledger entries are immutable — corrections append, never overwrite",
            "Reconciliation compares ledger balance to nameplate full charge",
          ]} />
        </div>
      </div>

      {/* Charge by circuit */}
      <div className="panel" style={{ overflow: "hidden" }}>
        <table className="table">
          <thead>
            <tr>
              <th>Circuit</th><th>Site</th><th>Refrigerant</th>
              <th className="num">Full charge ({prefs.massUnit})</th>
              <th className="num">Added (365d)</th>
              <th>
                Leak rate
                <HelpTip term="Annual leak rate">
                  Added over trailing 365 days ÷ full charge. 20% triggers the AIM Act repair window for commercial refrigeration.
                </HelpTip>
              </th>
            </tr>
          </thead>
          <tbody>
            {circuits.map((c) => {
              const rate = (c.addedLbs365 / c.fullChargeLbs) * 100;
              const level = rate >= 20 ? "critical" : rate >= 15 ? "warning" : "ok";
              return (
                <tr key={c.id}>
                  <td style={{ fontWeight: 600 }}>{c.name}</td>
                  <td>{sites.find((s) => s.id === c.siteId)?.name}</td>
                  <td className="num">{c.refrigerant}</td>
                  <td className="num">{fmtValue(c.fullChargeLbs, "mass", prefs, 0)}</td>
                  <td className="num">{fmtValue(c.addedLbs365, "mass", prefs, 0)}</td>
                  <td><StatusPill level={level} label={`${rate.toFixed(1)}%`} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Entries */}
      <div className="panel" style={{ overflow: "hidden" }}>
        <div style={{ padding: "var(--space-3) var(--space-4)", fontSize: "var(--text-xs)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", borderBottom: "1px solid var(--line-1)" }}>Entries</div>
        <table className="table">
          <thead><tr><th>Date</th><th>Circuit</th><th>Type</th><th className="num">Amount ({prefs.massUnit})</th><th>Technician</th><th>EPA cert</th><th>Cylinder</th></tr></thead>
          <tbody>
            {[...ledger].sort((a, b) => b.ts - a.ts).map((e) => {
              const site = sites.find((s) => s.id === e.siteId);
              return (
                <tr key={e.id}>
                  <td className="num" style={{ fontSize: "var(--text-xs)" }}>{fmtTime(e.ts, prefs, site?.tz ?? "UTC")}</td>
                  <td>{circuits.find((c) => c.id === e.circuitId)?.name}</td>
                  <td>{e.kind === "addition"
                    ? <StatusPill level="warning" label="Addition" />
                    : <StatusPill level="info" label="Recovery" />}</td>
                  <td className="num">{fmtValue(e.lbs, "mass", prefs, 1)}</td>
                  <td>{e.tech}</td>
                  <td className="num" style={{ fontSize: "var(--text-xs)" }}>{e.epaCert}</td>
                  <td className="num" style={{ fontSize: "var(--text-xs)" }}>{e.cylinder}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
