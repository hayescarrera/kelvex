/** Admin — users, roles, sites, notification routing. */
import { ScreenGuide, StatusPill } from "../components/core";
import { sites } from "../mock/engine";

const USERS = [
  { name: "Ben Linder", email: "ben@thelinders.com", role: "owner", sites: "All" },
  { name: "Maria Ruiz", email: "m.ruiz@example.com", role: "ops_manager", sites: "All" },
  { name: "Pat Doe", email: "pat@coolserv.com", role: "technician", sites: "Chicago DC" },
  { name: "Dana Fields", email: "dana@example.com", role: "finance", sites: "All" },
];

export function Admin() {
  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <h1 style={{ fontSize: 24 }}>Admin</h1>
        <div style={{ display: "flex", gap: "var(--space-3)" }}>
          <button className="btn primary">Invite user</button>
          <ScreenGuide items={[
            "Roles gate what users can do: technicians control equipment, viewers only read",
            "Non-admin users only see the sites you grant them",
            "Notification routing decides who gets paged for what severity, and when",
          ]} />
        </div>
      </div>

      <div className="panel" style={{ overflow: "hidden" }}>
        <div style={{ padding: "var(--space-3) var(--space-4)", fontSize: "var(--text-xs)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", borderBottom: "1px solid var(--line-1)" }}>Users & roles</div>
        <table className="table">
          <thead><tr><th>User</th><th>Role</th><th>Site access</th><th>Actions</th></tr></thead>
          <tbody>
            {USERS.map((u) => (
              <tr key={u.email}>
                <td><div style={{ fontWeight: 600 }}>{u.name}</div><div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>{u.email}</div></td>
                <td><StatusPill level="info" label={u.role} /></td>
                <td>{u.sites}</td>
                <td><div style={{ display: "flex", gap: 6 }}><button className="btn sm ghost">Edit role</button><button className="btn sm ghost">Sites…</button></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel" style={{ overflow: "hidden" }}>
        <div style={{ padding: "var(--space-3) var(--space-4)", fontSize: "var(--text-xs)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", borderBottom: "1px solid var(--line-1)" }}>Notification routing</div>
        <table className="table">
          <thead><tr><th>Rule</th><th>Severity</th><th>Channel</th><th>Quiet hours</th></tr></thead>
          <tbody>
            <tr><td>Critical → on-call, immediately</td><td><StatusPill level="critical" label="critical" /></td><td>SMS + Email</td><td>never quiet</td></tr>
            <tr><td>Warnings → site manager</td><td><StatusPill level="warning" label="warning" /></td><td>Email</td><td>22:00–06:00</td></tr>
            <tr><td>Daily digest → everyone</td><td><StatusPill level="info" label="info" /></td><td>Email 07:00</td><td>—</td></tr>
          </tbody>
        </table>
      </div>

      <div className="panel" style={{ overflow: "hidden" }}>
        <div style={{ padding: "var(--space-3) var(--space-4)", fontSize: "var(--text-xs)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", borderBottom: "1px solid var(--line-1)" }}>Sites</div>
        <table className="table">
          <thead><tr><th>Site</th><th>Timezone</th><th>Kind</th><th>Actions</th></tr></thead>
          <tbody>
            {sites.map((s) => (
              <tr key={s.id}>
                <td style={{ fontWeight: 600 }}>{s.name}</td>
                <td className="num" style={{ fontSize: "var(--text-xs)" }}>{s.tz}</td>
                <td>{s.kind === "grocery" ? "Grocery" : "Cold storage"}</td>
                <td><button className="btn sm ghost">Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
