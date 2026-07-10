/** Preferences — the granular controls, persisted per user. */
import { usePrefs, type Prefs } from "../state/prefs";
import { ScreenGuide } from "../components/core";
import { sites } from "../mock/engine";

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "var(--space-4)", alignItems: "center", padding: "var(--space-3) 0", borderBottom: "1px solid var(--line-1)" }}>
      <div>
        <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>{label}</div>
        {hint && <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>{hint}</div>}
      </div>
      <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", alignItems: "center" }}>{children}</div>
    </div>
  );
}

function Seg<K extends keyof Prefs>({ k, options }: { k: K; options: Array<{ v: Prefs[K]; label: string }> }) {
  const prefs = usePrefs();
  return (
    <div className="seg" role="group" aria-label={String(k)}>
      {options.map((o) => (
        <button key={String(o.v)} aria-pressed={prefs[k] === o.v} onClick={() => prefs.set(k, o.v)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

const ACCENTS: Array<{ v: Prefs["accent"]; c: string }> = [
  { v: "blue", c: "#3b82f6" }, { v: "cyan", c: "#06b6d4" },
  { v: "violet", c: "#8b5cf6" }, { v: "teal", c: "#14b8a6" },
];

export function Preferences() {
  const prefs = usePrefs();
  return (
    <div style={{ display: "grid", gap: "var(--space-4)", maxWidth: 860 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h1 style={{ fontSize: 24 }}>Preferences</h1>
        <ScreenGuide items={[
          "Everything here persists to your account and follows you across devices",
          "Semantic status colors (red/amber/green) are never affected by these settings",
        ]} />
      </div>

      <section className="panel" style={{ padding: "var(--space-5)" }}>
        <h2 style={{ fontSize: 16, marginBottom: "var(--space-3)" }}>Display</h2>
        <Row label="Density" hint="Row height and spacing across every table and list.">
          <Seg k="density" options={[{ v: "compact", label: "COMPACT" }, { v: "comfortable", label: "COMFORTABLE" }, { v: "spacious", label: "SPACIOUS" }]} />
        </Row>
        <Row label="Motion" hint="Defaults to your system's reduced-motion setting. Alarm states never animate regardless.">
          <Seg k="motion" options={[{ v: "full", label: "FULL" }, { v: "reduced", label: "REDUCED" }, { v: "none", label: "NONE" }]} />
        </Row>
        <Row label="Theme" hint="Light matches the rest of your tools; dark for overnight monitoring.">
          <Seg k="theme" options={[{ v: "dark", label: "DARK" }, { v: "light", label: "LIGHT" }, { v: "system", label: "SYSTEM" }]} />
        </Row>
        <Row label="Accent" hint="Never overrides status semantics.">
          <div style={{ display: "flex", gap: 8 }}>
            {ACCENTS.map((a) => (
              <button key={a.v} aria-label={`Accent ${a.v}`} aria-pressed={prefs.accent === a.v}
                onClick={() => prefs.set("accent", a.v)}
                style={{
                  width: 34, height: 34, borderRadius: "50%", background: a.c,
                  border: prefs.accent === a.v ? "3px solid var(--ink-1)" : "3px solid transparent",
                }} />
            ))}
          </div>
        </Row>
      </section>

      <section className="panel" style={{ padding: "var(--space-5)" }}>
        <h2 style={{ fontSize: 16, marginBottom: "var(--space-3)" }}>Units & time</h2>
        <Row label="Temperature"><Seg k="tempUnit" options={[{ v: "F", label: "°F" }, { v: "C", label: "°C" }]} /></Row>
        <Row label="Pressure"><Seg k="pressureUnit" options={[{ v: "psi", label: "PSI" }, { v: "kPa", label: "kPa" }]} /></Row>
        <Row label="Mass"><Seg k="massUnit" options={[{ v: "lb", label: "LB" }, { v: "kg", label: "KG" }]} /></Row>
        <Row label="Timestamps" hint="Compliance documents always record both; this sets what you see.">
          <Seg k="tzMode" options={[{ v: "site", label: "SITE-LOCAL" }, { v: "user", label: "MY TIME" }]} />
        </Row>
      </section>

      <section className="panel" style={{ padding: "var(--space-5)" }}>
        <h2 style={{ fontSize: 16, marginBottom: "var(--space-3)" }}>Defaults</h2>
        <Row label="Landing view">
          <select className="select" style={{ maxWidth: 260 }} value={prefs.defaultLanding} onChange={(e) => prefs.set("defaultLanding", e.target.value)}>
            <option value="/">Fleet overview</option>
            <option value="/alarms">Alarm inbox</option>
            <option value="/leaks">Leak events</option>
          </select>
        </Row>
        <Row label="Default site">
          <select className="select" style={{ maxWidth: 260 }} value={prefs.defaultSiteId ?? ""} onChange={(e) => prefs.set("defaultSiteId", e.target.value || null)}>
            <option value="">All sites</option>
            {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Row>
        <Row label="Default time range">
          <Seg k="defaultRangeHours" options={[{ v: 6, label: "6H" }, { v: 24, label: "24H" }, { v: 168, label: "7D" }]} />
        </Row>
        <Row label="Chart style">
          <Seg k="chartStyle" options={[{ v: "line", label: "LINE" }, { v: "step", label: "STEP" }, { v: "area", label: "AREA" }]} />
        </Row>
      </section>
    </div>
  );
}
