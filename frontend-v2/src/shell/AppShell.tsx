/**
 * App shell: top bar (mode switch — instant, no reload), left nav,
 * command palette, shortcuts overlay. The mode toggle is the product's
 * signature move: one keystroke between Field and Command.
 */
import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { usePrefs, applyPrefsToDocument } from "../state/prefs";
import { CommandPalette } from "../components/CommandPalette";
import { alarms, leakEvents } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { StatusPill } from "../components/core";

const NAV = [
  { to: "/", label: "Fleet", icon: "▦" },
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
    ["⌘K / Ctrl+K", "Command palette"],
    ["M", "Toggle Field / Command mode"],
    ["G then F / A / L", "Go to Fleet / Alarms / Leaks"],
    ["A", "Acknowledge selected alarm"],
    ["J / K", "Next / previous row"],
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
  const prefs = usePrefs();
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
      if (e.key.toLowerCase() === "m") { usePrefs.getState().toggleMode(); return; }
      if (e.key.toLowerCase() === "g") { goPending = true; setTimeout(() => (goPending = false), 800); return; }
      if (goPending) {
        const map: Record<string, string> = { f: "/", a: "/alarms", l: "/leaks" };
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
    <div style={{ display: "grid", gridTemplateRows: "auto 1fr", height: "100%" }}>
      {/* ── Top bar ── */}
      <header
        style={{
          display: "flex", alignItems: "center", gap: "var(--space-4)",
          padding: "0 var(--space-4)", height: 60,
          borderBottom: "var(--border-w) solid var(--line-1)",
          background: "var(--surface-glass)",
          backdropFilter: "blur(var(--glass-blur))",
          position: "sticky", top: 0, zIndex: 40,
        }}
      >
        <NavLink to="/" style={{ textDecoration: "none", display: "flex", alignItems: "baseline", gap: 8 }}>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 18, letterSpacing: "0.08em" }}>KELVEX</span>
          <span className="num" style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>ops</span>
        </NavLink>

        {/* Mode switch — the signature control. Instant. */}
        <div className="seg" role="group" aria-label="Display mode">
          <button aria-pressed={prefs.mode === "field"} onClick={() => prefs.set("mode", "field")}>FIELD</button>
          <button aria-pressed={prefs.mode === "command"} onClick={() => prefs.set("mode", "command")}>COMMAND</button>
        </div>

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
          <button className="btn sm" onClick={() => setPaletteOpen(true)} aria-label="Open command palette">
            ⌘K <span className="icon-label">Search</span>
          </button>
          <NavLink to="/preferences" className="btn sm ghost" aria-label="Preferences" style={{ textDecoration: "none" }}>
            ⚙ <span className="icon-label">Preferences</span>
          </NavLink>
        </div>
      </header>

      {/* ── Body ── */}
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", minHeight: 0 }}>
        <nav aria-label="Primary" style={{ borderRight: "var(--border-w) solid var(--line-1)", padding: "var(--space-3) var(--space-2)", background: "var(--surface-1)", minWidth: prefs.mode === "field" ? 170 : 150 }}>
          {NAV.map((n) => (
            <NavLink
              key={n.to} to={n.to} end={n.to === "/"}
              style={({ isActive }) => ({
                display: "flex", alignItems: "center", gap: 10,
                minHeight: "var(--hit)", padding: "0 var(--space-3)",
                borderRadius: "var(--radius-sm)", textDecoration: "none",
                fontWeight: 550, fontSize: "var(--text-sm)",
                color: isActive ? "var(--ink-1)" : "var(--ink-2)",
                background: isActive ? "var(--accent-soft)" : "transparent",
                borderLeft: isActive ? "3px solid var(--accent)" : "3px solid transparent",
                marginBottom: 2,
              })}
            >
              <span aria-hidden style={{ width: 16, textAlign: "center" }}>{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <main style={{ overflow: "auto", padding: "var(--space-5)", minWidth: 0 }}>
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <ShortcutsOverlay open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}
