# Kelvex Ops — Design Spec

The app for people who have stood in a cold room at 2am. Two first-class
users: a tech on a gloved tablet in a 34°F warehouse, and a compliance lead
on an office laptop. One product, two presentations (see MODES.md).

## Token system

All values live in `src/styles/tokens.css` as CSS custom properties on
`<html>`, switched by five attributes:

| Attribute | Values | Default |
|---|---|---|
| `data-mode` | `field` \| `command` | command |
| `data-theme` | `dark` \| `light` (from `system` pref) | dark |
| `data-density` | `compact` \| `comfortable` \| `spacious` | comfortable |
| `data-motion` | `full` \| `reduced` \| `none` | system `prefers-reduced-motion` |
| `data-accent` | `blue` \| `cyan` \| `violet` \| `teal` | blue |

Prefs persist per user (`src/state/prefs.ts`, zustand + persist; production
hydrates the same shape from the API). Switching is attribute assignment —
no reload, no remount.

### Color

- Anchored on the deep-blue instrument aesthetic of kelvex.io.
- Dark theme surfaces: `#070b14 → #0c1220 → #111a2e → #17223a` (page →
  panel → raised → highest). Field mode collapses the top two.
- **Status colors are sacred**: red `#ef4444`, amber `#f59e0b`, green
  `#22c55e`, info `#38bdf8`, stale `#8b93a7`. Reserved exclusively for
  state; unreachable by accent/theme/mode.

### Type

- **Space Grotesk** — display (headings, big numbers with character)
- **Inter** — UI text, `font-feature-settings: "tnum"` globally
- **JetBrains Mono** — telemetry values, timestamps, IDs (`.num`)
- Tabular numerals on every numeric column, no exceptions.

## Screen inventory

| Route | Screen | Depth |
|---|---|---|
| `/` | Fleet overview — the "am I okay?" screen | full |
| `/sites/:id` | Site detail — schematic (Command) / nested table (Field) | full |
| `/assets/:id` | Asset detail — live charts, brush-zoom, setpoints, service history | full |
| `/alarms` | Alarm inbox — triage-first, J/K/A/S/N keyboard flow | full |
| `/leaks` | Leak events — stage track, repair clock, missing-to-close | full |
| `/ledger` | Refrigerant ledger — charge, additions/recoveries, leak rates | full |
| `/compliance` | AIM Act posture + inspector-exact export preview | full |
| `/agents` | Edge agent health — connectivity, mapping progress | full |
| `/admin` | Users, roles, sites, notification routing | functional |
| `/preferences` | All user overrides | full |

## Component list

`StatusPill` · `TweenNumber` · `SensorValue` (provenance popover) ·
`RepairClock` · `StatTile` · `EmptyState` · `HelpTip` (inline compliance
explainers) · `ScreenGuide` ("What can I do here?") · `LiveChart` (uPlot,
canvas, live tail, drag-zoom) · `CommandPalette` (⌘K) · `ShortcutsOverlay` ·
`AppShell` (top bar with mode switch, nav)

## Non-negotiables, and where they're enforced

| Constraint | Enforcement |
|---|---|
| Alarm state never animates | `base.css`: `.pill.critical { transition: none !important; animation: none !important }` |
| Stale looks stale | `isStale()` gates every `SensorValue`; `.stale-wash` + STALE pill + timestamp |
| Repair clock always visible | `RepairClock` rendered on Fleet rollup, site rows, site tiles, asset header, leaks, compliance |
| Every number has provenance | `SensorValue` popover: device, freshness, unit, raw/derived |
| Nothing destructive without recourse | compliance records immutable; ledger corrections append |
| Color never alone | `StatusPill` = glyph + label + color, used exclusively for state |

## Discoverability

- Empty states name what belongs, why, and the next action (`EmptyState`).
- ⌘K palette reaches every screen, site, asset, and action by plain name.
- `?` HelpTips define every compliance term in two sentences.
- Every screen has a "What can I do here?" listing its capabilities.
- `?` key shows the shortcut overlay; J/K/A/S/N drive the alarm inbox;
  M toggles mode; G-then-F/A/L navigates.

## Data layer

`src/mock/engine.ts` simulates the fleet cold: 2s tick, mean-reverting
telemetry with a daily cycle, ring-buffer history per sensor (uPlot-ready
Float64Arrays), a defrost that advances, a compressor that short-cycles, a
sensor that has been silent 22 minutes (stale path), a live alarm that fires
~90s into a demo, and an open leak event whose 30-day clock sits at 6 days.
Replace by implementing the same interfaces against the real API; screens
subscribe through `useLiveTick()` (`useSyncExternalStore`).

## Performance

- uPlot canvas charts (no SVG re-render churn), seeded with 24h and tailing
  live without allocation.
- Skeleton-free: layouts are stable; states swap in place (no CLS).
- Bundle: ~117KB gzipped including charts; single code-split point ready at
  the router when screens grow.
