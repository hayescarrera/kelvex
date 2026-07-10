/** Compliance & reporting — AIM Act posture + preview of the audit package. */
import { circuits, leakEvents, sites } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { HelpTip, RepairClock, ScreenGuide, StatTile, StatusPill } from "../components/core";

export function Compliance() {
  useLiveTick();
  const above = circuits.filter((c) => (c.addedLbs365 / c.fullChargeLbs) * 100 >= 20);
  const open = leakEvents.filter((l) => l.stage !== "closed");

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <h1 style={{ fontSize: 24 }}>Compliance & reporting</h1>
        <ScreenGuide items={[
          "AIM Act posture across every circuit, updated as the ledger changes",
          "The export is exactly what an inspector receives — preview before sending",
          "Records are immutable; every export is reproducible from the ledger",
        ]} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--space-4)" }}>
        <StatTile label="Circuits above 20%" level={above.length ? "critical" : "ok"}
          value={<span className="num">{above.length}</span>}
          sub={above.length ? above.map((c) => c.name).join(", ") : "All within threshold"} />
        <StatTile label="Open repair windows" level={open.length ? "warning" : "ok"}
          value={<span className="num">{open.length}</span>}
          sub={open.length ? <RepairClock deadline={open[0].repairDeadline} compact /> : "None running"} />
        <StatTile label="Records exportable"
          value={<span className="num">365d</span>}
          sub="Leak rates, additions, events, repairs" />
      </div>

      {/* Export preview — what the inspector sees */}
      <div className="panel" style={{ padding: "var(--space-5)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
          <div>
            <h2 style={{ fontSize: 18 }}>
              AIM Act audit package
              <HelpTip term="Audit package">
                A ZIP of four CSVs (leak rates, additions, leak events, repairs) plus a methodology README
                citing the EPA annualizing method under 40 CFR Part 84. Generated from the live ledger.
              </HelpTip>
            </h2>
            <p style={{ color: "var(--ink-2)", fontSize: "var(--text-sm)", maxWidth: "60ch" }}>
              This preview mirrors the exact files an inspector receives. Nothing is edited on export —
              if the preview looks wrong, fix the ledger, not the report.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn primary">Export ZIP</button>
            <button className="btn">Export PDF summary</button>
          </div>
        </div>

        <div className="panel-2" style={{ padding: "var(--space-4)", fontFamily: "var(--font-data)", fontSize: "var(--text-xs)", overflow: "auto" }}>
          <div style={{ color: "var(--ink-3)", marginBottom: 8 }}>leak_rate_summary.csv — preview</div>
          <table className="table" style={{ fontSize: "var(--text-xs)" }}>
            <thead><tr><th>facility</th><th>circuit</th><th>refrigerant</th><th className="num">full_charge_lbs</th><th className="num">added_lbs_365d</th><th className="num">annual_leak_rate_pct</th><th>compliance_status</th></tr></thead>
            <tbody>
              {circuits.map((c) => {
                const rate = (c.addedLbs365 / c.fullChargeLbs) * 100;
                return (
                  <tr key={c.id}>
                    <td>{sites.find((s) => s.id === c.siteId)?.name}</td>
                    <td>{c.name}</td>
                    <td>{c.refrigerant}</td>
                    <td className="num">{c.fullChargeLbs}</td>
                    <td className="num">{c.addedLbs365}</td>
                    <td className="num" style={{ color: rate >= 20 ? "var(--status-critical)" : undefined }}>{rate.toFixed(2)}</td>
                    <td>{rate >= 20 ? "EXCEEDS THRESHOLD — repair required" : rate >= 15 ? "Warning — approaching threshold" : "Compliant"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Posture table */}
      <div className="panel" style={{ overflow: "hidden" }}>
        <table className="table">
          <thead><tr><th>Circuit</th><th>Status</th><th>Open events</th><th>Documentation</th></tr></thead>
          <tbody>
            {circuits.map((c) => {
              const rate = (c.addedLbs365 / c.fullChargeLbs) * 100;
              const evt = leakEvents.find((l) => l.circuitId === c.id && l.stage !== "closed");
              return (
                <tr key={c.id}>
                  <td style={{ fontWeight: 600 }}>{c.name}</td>
                  <td><StatusPill level={rate >= 20 ? "critical" : rate >= 15 ? "warning" : "ok"} label={`${rate.toFixed(1)}% / 20%`} /></td>
                  <td>{evt ? <RepairClock deadline={evt.repairDeadline} compact /> : <span style={{ color: "var(--ink-3)" }}>none</span>}</td>
                  <td style={{ fontSize: "var(--text-xs)", color: evt?.missingToClose.length ? "var(--status-warning)" : "var(--ink-3)" }}>
                    {evt?.missingToClose.length ? `${evt.missingToClose.length} items missing to close` : "Complete"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
