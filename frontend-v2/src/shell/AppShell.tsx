/**
 * App shell — category-standard chrome: white top bar with global search,
 * labeled left sidebar, alarm/leak indicators, user chip. ⌘K everywhere.
 */
import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { CommandPalette } from "../components/CommandPalette";
import { alarms, leakEvents } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { StatusPill } from "../components/core";
import { applyPrefsToDocument, usePrefs } from "../state/prefs";

const NAV = [
  { to: "/", label: "Dashboard", icon: "▦" },
  { to: "/alarms", label: "Alarms", icon: "◆" },
  { to: "/leaks", label: "Leak events", icon: "◉" },
  { to: "/ledger", label: "Refrigerant", icon: "☰" },
  { to: "/compliance", label: "Compliance", icon: "✓" },
  { to: "/agents", label: "Edge agents", icon: "⇄" },
  { to: "/admin", label: "Admin", icon: "⚙" },
];

function ShortcutsOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  const rows: Array<[string, string]> = [
    ["⌘K / Ctrl+K", "Search & commands"],
    ["G then D / A / L", "Go to Dashboard / Alarms / Leaks"],
    ["J / K", "Next / previous row (alarm inbox)"],
    ["A / S / N", "Acknowledge / snooze / note selected alarm"],
    ["?", "This overlay"],
    ["Esc", "Close any overlay"],
  ];
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="popover" role="dialog" aria-label="Keyboard shortcuts"
        style={{ position: "fixed", zIndex: 70, left: "50%", top: "20vh", transform: "translateX(-50%)", minWidth: 380 }}>
        <h3 style={{ marginBottom: 12 }}>Keyboard shortcuts</h3>
        <table style={{ width: "100%", fontSize: "var(--text-sm)" }}>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <td style={{ padding: "6px 16px 6px 0" }}><kbd className="num" style={{ background: "var(--surface-0)", border: "1px solid var(--line-2)", borderRadius: 4, padding: "2px 8px", fontSize: "var(--text-xs)" }}>{k}</kbd></td>
                <td style={{ color: "var(--ink-2)" }}>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function AppShell() {
  const nav = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  useLiveTick();

  useEffect(() => { applyPrefsToDocument(usePrefs.getState()); }, []);

  useEffect(() => {
    let goPending = false;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setPaletteOpen((o) => !o); return;
      }
      if (typing) return;
      if (e.key === "?") { setShortcutsOpen((o) => !o); return; }
      if (e.key === "Escape") { setPaletteOpen(false); setShortcutsOpen(false); return; }
      if (e.key.toLowerCase() === "g") { goPending = true; setTimeout(() => (goPending = false), 800); return; }
      if (goPending) {
        const map: Record<string, string> = { d: "/", a: "/alarms", l: "/leaks" };
        const to = map[e.key.toLowerCase()];
        if (to) nav(to);
        goPending = false;
      }
    };
    const onShortcutsEvt = () => setShortcutsOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("kelvex:shortcuts", onShortcutsEvt);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("kelvex:shortcuts", onShortcutsEvt); };
  }, [nav]);

  const activeAlarms = alarms.filter((a) => a.state === "active");
  const criticalCount = activeAlarms.filter((a) => a.severity === "critical").length;
  const openLeaks = leakEvents.filter((l) => l.stage !== "closed");

  return (
    <div style={{ display: "grid", gridTemplateColumns: "216px 1fr", height: "100%" }}>
      {/* ── Sidebar ── */}
      <nav aria-label="Primary" style={{
        display: "flex", flexDirection: "column",
        borderRight: "1px solid var(--line-1)", background: "var(--surface-1)",
        padding: "var(--space-4) var(--space-3)",
      }}>
        <NavLink to="/" style={{ textDecoration: "none", display: "flex", alignItems: "baseline", gap: 8, padding: "0 var(--space-2) var(--space-4)" }}>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 17, letterSpacing: "0.06em" }}>KELVEX</span>
        </NavLink>
        {NAV.map((n) => (
          <NavLink
            key={n.to} to={n.to} end={n.to === "/"}
            style={({ isActive }) => ({
              display: "flex", alignItems: "center", gap: 10,
              minHeight: 38, padding: "0 var(--space-3)",
              borderRadius: "var(--radius-sm)", textDecoration: "none",
              fontWeight: 550, fontSize: "var(--text-sm)",
              color: isActive ? "var(--accent-strong)" : "var(--ink-2)",
              background: isActive ? "var(--accent-soft)" : "transparent",
              marginBottom: 2,
            })}
          >
            <span aria-hidden style={{ width: 16, textAlign: "center" }}>{n.icon}</span>
            {n.label}
            {n.to === "/alarms" && activeAlarms.length > 0 && (
              <span className="num" style={{
                marginLeft: "auto", fontSize: 11, fontWeight: 700,
                background: criticalCount ? "var(--status-critical)" : "var(--status-warning)",
                color: "#fff", borderRadius: 999, padding: "1px 7px",
              }}>{activeAlarms.length}</span>
            )}
          </NavLink>
        ))}
        <div style={{ marginTop: "auto", borderTop: "1px solid var(--line-1)", paddingTop: "var(--space-3)" }}>
          <NavLink to="/preferences" style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: 10, minHeight: 38,
            padding: "0 var(--space-3)", borderRadius: "var(--radius-sm)",
            textDecoration: "none", fontWeight: 550, fontSize: "var(--text-sm)",
            color: isActive ? "var(--accent-strong)" : "var(--ink-2)",
            background: isActive ? "var(--accent-soft)" : "transparent",
          })}>
            <span aria-hidden style={{ width: 16, textAlign: "center" }}>☼</span>
            Preferences
          </NavLink>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "var(--space-3) var(--space-3) 0" }}>
            <span aria-hidden style={{
              width: 28, height: 28, borderRadius: "50%", background: "var(--accent-soft)",
              color: "var(--accent-strong)", display: "inline-flex", alignItems: "center",
              justifyContent: "center", fontWeight: 700, fontSize: 12,
            }}>BL</span>
            <div style={{ lineHeight: 1.25 }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 650 }}>Ben Linder</div>
              <div style={{ fontSize: 10.5, color: "var(--ink-3)" }}>Owner</div>
            </div>
          </div>
        </div>
      </nav>

      {/* ── Main column ── */}
      <div style={{ display: "grid", gridTemplateRows: "auto 1fr", minWidth: 0 }}>
        <header style={{
          display: "flex", alignItems: "center", gap: "var(--space-3)",
          padding: "0 var(--space-5)", height: 56,
          borderBottom: "1px solid var(--line-1)", background: "var(--surface-1)",
        }}>
          <button className="btn sm" onClick={() => setPaletteOpen(true)}
            style={{ color: "var(--ink-3)", fontWeight: 450, minWidth: 260, justifyContent: "flex-start" }}
            aria-label="Search sites, assets, actions">
            🔍 Search sites, assets, actions… <kbd className="num" style={{ marginLeft: "auto", fontSize: 10.5, border: "1px solid var(--line-2)", borderRadius: 4, padding: "0 5px" }}>⌘K</kbd>
          </button>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            {criticalCount > 0 && (
              <NavLink to="/alarms" style={{ textDecoration: "none" }}>
                <StatusPill level="critical" label={`${criticalCount} critical`} />
              </NavLink>
            )}
            {openLeaks.length > 0 && (
              <NavLink to="/leaks" style={{ textDecoration: "none" }}>
                <StatusPill level="warning" label={`${openLeaks.length} open leak`} />
              </NavLink>
            )}
          </div>
        </header>
        <main style={{ overflow: "auto", padding: "var(--space-5)", minWidth: 0, background: "var(--surface-0)" }}>
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <ShortcutsOverlay open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}
