/**
 * ⌘K command palette — every screen, asset, site, and action reachable by
 * plain-language name. The discoverability backbone.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { assets, sites, ackAlarm, alarms } from "../mock/engine";
import { usePrefs } from "../state/prefs";

interface Command {
  id: string;
  title: string;
  hint?: string;
  group: "Navigate" | "Sites" | "Assets" | "Actions" | "Help";
  run: () => void;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate();
  const prefs = usePrefs();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands = useMemo<Command[]>(() => [
    { id: "go-fleet", title: "Go to Fleet overview", group: "Navigate", run: () => nav("/") },
    { id: "go-alarms", title: "Go to Alarm inbox", group: "Navigate", run: () => nav("/alarms") },
    { id: "go-leaks", title: "Go to Leak events", group: "Navigate", run: () => nav("/leaks") },
    { id: "go-ledger", title: "Go to Refrigerant ledger", group: "Navigate", run: () => nav("/ledger") },
    { id: "go-compliance", title: "Go to Compliance & reporting", group: "Navigate", run: () => nav("/compliance") },
    { id: "go-agents", title: "Go to Edge agent health", group: "Navigate", run: () => nav("/agents") },
    { id: "go-admin", title: "Go to Admin", group: "Navigate", run: () => nav("/admin") },
    { id: "go-prefs", title: "Open Preferences", hint: "display mode, units, theme", group: "Navigate", run: () => nav("/preferences") },
    ...sites.map((s) => ({
      id: `site-${s.id}`, title: `Jump to ${s.name}`, hint: s.city, group: "Sites" as const,
      run: () => nav(`/sites/${s.id}`),
    })),
    ...assets.map((a) => ({
      id: `asset-${a.id}`, title: `Open ${a.name}`, hint: sites.find((s) => s.id === a.siteId)?.name, group: "Assets" as const,
      run: () => nav(`/assets/${a.id}`),
    })),
    {
      id: "act-mode", title: `Switch to ${prefs.mode === "field" ? "Command" : "Field"} mode`,
      hint: "instant, no reload", group: "Actions", run: () => prefs.toggleMode(),
    },
    {
      id: "act-ack-all", title: "Acknowledge all active alarms", hint: "marks them seen, keeps them open",
      group: "Actions", run: () => alarms.filter((a) => a.state === "active").forEach((a) => ackAlarm(a.id)),
    },
    { id: "act-export", title: "Export audit package (AIM Act)", hint: "ZIP: CSVs + methodology", group: "Actions", run: () => nav("/compliance") },
    { id: "help-shortcuts", title: "Show keyboard shortcuts", hint: "?", group: "Help", run: () => window.dispatchEvent(new CustomEvent("kelvex:shortcuts")) },
  ], [nav, prefs]);

  const results = useMemo(() => {
    if (!q.trim()) return commands;
    const terms = q.toLowerCase().split(/\s+/);
    return commands.filter((c) =>
      terms.every((t) => (c.title + " " + (c.hint ?? "")).toLowerCase().includes(t)),
    );
  }, [q, commands]);

  useEffect(() => { if (open) { setQ(""); setSel(0); setTimeout(() => inputRef.current?.focus(), 10); } }, [open]);
  useEffect(() => { setSel(0); }, [q]);

  if (!open) return null;

  const runSelected = () => {
    const cmd = results[sel];
    if (cmd) { cmd.run(); onClose(); }
  };

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div
        role="dialog" aria-label="Command palette"
        style={{
          position: "fixed", zIndex: 70, left: "50%", top: "12vh",
          transform: "translateX(-50%)", width: "min(640px, 92vw)",
          background: "var(--surface-3)", border: "var(--border-w) solid var(--line-2)",
          borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-2)", overflow: "hidden",
        }}
      >
        <input
          ref={inputRef}
          className="input"
          style={{ border: 0, borderBottom: "var(--border-w) solid var(--line-1)", borderRadius: 0, background: "transparent", minHeight: 56, fontSize: "var(--text-lg)" }}
          placeholder="Search screens, sites, assets, actions…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, results.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
            if (e.key === "Enter") runSelected();
            if (e.key === "Escape") onClose();
          }}
        />
        <div style={{ maxHeight: "50vh", overflow: "auto", padding: 6 }}>
          {results.length === 0 && (
            <div style={{ padding: "var(--space-4)", color: "var(--ink-2)" }}>
              Nothing matches "{q}". Try an asset name, a site, or a verb like "export".
            </div>
          )}
          {results.map((c, i) => (
            <button
              key={c.id}
              onMouseEnter={() => setSel(i)}
              onClick={() => { c.run(); onClose(); }}
              style={{
                display: "flex", width: "100%", alignItems: "center", gap: 10,
                padding: "10px 12px", borderRadius: "var(--radius-sm)", textAlign: "left",
                background: i === sel ? "var(--accent-soft)" : "transparent",
                minHeight: "var(--hit)",
              }}
            >
              <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--ink-3)", width: 74, flexShrink: 0, textTransform: "uppercase" }}>{c.group}</span>
              <span style={{ fontWeight: 550 }}>{c.title}</span>
              {c.hint && <span style={{ color: "var(--ink-3)", fontSize: "var(--text-xs)", marginLeft: "auto" }}>{c.hint}</span>}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
