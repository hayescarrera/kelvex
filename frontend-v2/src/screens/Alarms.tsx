/**
 * Alarm inbox — triage-first, keyboard-driven.
 * J/K to move, A to acknowledge, S to snooze, N to annotate.
 * Critical rows render at full contrast with zero animation.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { alarms, assets, sites, ackAlarm, snoozeAlarm, assignAlarm, annotateAlarm } from "../mock/engine";
import { useLiveTick } from "../mock/useLive";
import { EmptyState, ScreenGuide, StatusPill } from "../components/core";
import { ago } from "../lib/format";

type Filter = "all" | "active" | "acknowledged" | "snoozed";

export function Alarms() {
  useLiveTick();
  const nav = useNavigate();
  const [filter, setFilter] = useState<Filter>("active");
  const [sel, setSel] = useState(0);
  const [noteFor, setNoteFor] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const rows = useMemo(() => {
    const list = filter === "all" ? alarms : alarms.filter((a) => a.state === filter);
    const order = { critical: 0, warning: 1, info: 2 };
    return [...list].sort((a, b) => order[a.severity] - order[b.severity] || b.raisedAt - a.raisedAt);
  }, [filter, useLiveTick()]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setSel((s) => Math.min(s, Math.max(0, rows.length - 1))); }, [rows.length]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key.toLowerCase() === "j") setSel((s) => Math.min(s + 1, rows.length - 1));
      if (e.key.toLowerCase() === "k") setSel((s) => Math.max(s - 1, 0));
      if (e.key.toLowerCase() === "a" && rows[sel]) ackAlarm(rows[sel].id);
      if (e.key.toLowerCase() === "s" && rows[sel]) snoozeAlarm(rows[sel].id);
      if (e.key.toLowerCase() === "n" && rows[sel]) setNoteFor(rows[sel].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, sel]);

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <h1 style={{ fontSize: 24 }}>Alarm inbox</h1>
        <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
          <div className="seg" role="group" aria-label="Filter alarms">
            {(["active", "acknowledged", "snoozed", "all"] as Filter[]).map((f) => (
              <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {f.toUpperCase()}
              </button>
            ))}
          </div>
          <ScreenGuide items={[
            "J/K moves the selection, A acknowledges, S snoozes, N adds a note",
            "Acknowledging marks an alarm seen — it stays open until the condition clears",
            "Click the asset name to jump to its live telemetry",
            "Critical alarms always sort to the top",
          ]} />
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title={filter === "active" ? "No active alarms" : `No ${filter} alarms`}
          body="Alarms appear here the moment a sensor crosses a threshold, a device stops reporting, or a compressor misbehaves. They stay until acknowledged and resolved."
          action="Review alarm routing"
          onAction={() => nav("/admin")}
        />
      ) : (
        <div className="panel" style={{ overflow: "hidden" }}>
          <table className="table">
            <thead>
              <tr><th style={{ width: 110 }}>Severity</th><th>Alarm</th><th>Asset</th><th>Raised</th><th>State</th><th style={{ width: 260 }}>Actions</th></tr>
            </thead>
            <tbody>
              {rows.map((a, i) => {
                const asset = assets.find((x) => x.id === a.assetId);
                const site = sites.find((x) => x.id === a.siteId);
                return (
                  <tr key={a.id}
                    style={{
                      background: i === sel ? "var(--accent-soft)" : undefined,
                      borderLeft: a.severity === "critical" ? "4px solid var(--status-critical)" : "4px solid transparent",
                    }}
                    onClick={() => setSel(i)}
                  >
                    <td><StatusPill level={a.severity === "info" ? "info" : a.severity} label={a.severity} /></td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{a.title}</div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-2)", maxWidth: 420 }}>{a.detail}</div>
                      {a.notes.length > 0 && (
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)", marginTop: 2 }}>📝 {a.notes[a.notes.length - 1]}</div>
                      )}
                    </td>
                    <td>
                      <button className="btn ghost sm" onClick={(e) => { e.stopPropagation(); nav(`/assets/${a.assetId}`); }}>
                        {asset?.name}
                      </button>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)", paddingLeft: 12 }}>{site?.name}</div>
                    </td>
                    <td className="num" style={{ fontSize: "var(--text-xs)" }}>{ago(a.raisedAt)}</td>
                    <td>
                      {a.state === "active" && <StatusPill level="warning" label="Active" />}
                      {a.state === "acknowledged" && <StatusPill level="info" label={`Ack · ${a.ackBy}`} />}
                      {a.state === "snoozed" && <StatusPill level="stale" label="Snoozed" />}
                      {a.assignee && <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)", marginTop: 2 }}>→ {a.assignee}</div>}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {a.state === "active" && <button className="btn sm" onClick={(e) => { e.stopPropagation(); ackAlarm(a.id); }}>Ack</button>}
                        <button className="btn sm ghost" onClick={(e) => { e.stopPropagation(); assignAlarm(a.id, "P. Doe"); }}>Assign</button>
                        <button className="btn sm ghost" onClick={(e) => { e.stopPropagation(); snoozeAlarm(a.id); }}>Snooze</button>
                        <button className="btn sm ghost" onClick={(e) => { e.stopPropagation(); setNoteFor(a.id); setNote(""); }}>Note</button>
                      </div>
                      {noteFor === a.id && (
                        <form
                          style={{ display: "flex", gap: 6, marginTop: 6 }}
                          onSubmit={(e) => { e.preventDefault(); if (note.trim()) annotateAlarm(a.id, note.trim()); setNoteFor(null); }}
                        >
                          <input autoFocus className="input" style={{ minHeight: 36, fontSize: "var(--text-xs)" }}
                            placeholder="Add a note and press Enter" value={note} onChange={(e) => setNote(e.target.value)} />
                        </form>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
