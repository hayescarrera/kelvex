# MODES.md — what actually changes between Field and Command

One component tree. Two themes' worth of tokens. If you find yourself
writing `if (mode === "field")` in a component for anything other than a
*structural* swap (schematic vs table), stop — it belongs in `tokens.css`.

## The rule

**Field** is not the ugly mode. It is the mode a professional chooses
because it is faster: flat, hard-edged, bigger, stiller. **Command** is the
full instrument: depth, ambient motion, schematics. Same information
architecture, same routes, same data, same features. Only presentation.

## Token diff (authoritative)

| Token | Command | Field | Why |
|---|---|---|---|
| `--radius-sm / --radius / --radius-lg` | 6 / 10 / 14px | 2 / 3 / 4px | Hard edges read faster in glare |
| `--border-w` | 1px | 2px | Borders replace shadows for separation |
| `--shadow-1 / --shadow-2` | layered shadows | `none` | No depth theatrics in the field |
| `--inner-stroke` | subtle inner highlight | `none` | Glass only where it earns its place |
| `--glass-blur` | 14px | 0px | No blur on low-end hardware |
| `--tile-gradient` | faint top sheen | `none` | Flat surfaces |
| `--surface-2 / --surface-3` | raised layers | collapse to `--surface-1` | Flat hierarchy, higher contrast |
| `--line-1` | hairline | promoted to `--line-2` | Every boundary visible |
| `--ink-2` (dark) | #9aa6bf | #b3bdd4 | Secondary text lifted for glare |
| `--text-base / sm / xs / lg` | 15 / 13 / 11.5 / 17px | 16 / 14 / 12.5 / 18px | Bigger base type |
| `--leading` | 1.55 | 1.6 | Generous line height |
| `--hit` | 48px | 52px | Glove targets (48px is the floor everywhere) |
| `--ambient` | 1 | 0 | Kills breathing tiles, pulse effects, stagger |
| `--label-icons` | `none` | `inline` | Text labels beside every icon |

Density (`compact/comfortable/spacious`) and motion (`full/reduced/none`)
are orthogonal axes; Field clamps compact's row height to 44px so gloves
still work, and forces `--ambient: 0` regardless of the motion setting.

## Structural swaps (the only allowed `mode` branches in JSX)

1. **Site detail**: Command renders the schematic tile grid; Field renders
   the nested table. Same assets, same click targets.
2. **Asset charts**: Field stacks charts one per row (bigger, scannable);
   Command uses a responsive grid.
3. **Chart count/decoration**: numbers-over-sparklines in Field is achieved
   by tokens (no ambient, no gradients) — not by removing data.

## What never changes, in either mode

- Status = icon + text label + color. Always all three.
- Critical/alarm state renders instantly: `transition: none` is enforced on
  `.pill.critical` in CSS, not left to component discipline.
- Stale data is desaturated, timestamped, and labeled STALE.
- The repair clock appears everywhere the affected asset appears.
- Provenance popovers on every telemetry number.
- Semantic status colors are immune to theme, mode, and accent choice.

## Motion spec

| Token | Value |
|---|---|
| `--dur-fast` | 120ms — hovers, toggles |
| `--dur-base` | 200ms — reveals, list entry |
| `--dur-slow` | 320ms — drawers, sheets |
| ceiling | nothing exceeds 400ms; everything interruptible |
| `--ease-out` | cubic-bezier(0.22, 1, 0.36, 1) |
| `--ease-spring` | cubic-bezier(0.34, 1.4, 0.64, 1) — drawers only |

`data-motion="none"` zeroes all three durations. `reduced` keeps functional
feedback and zeroes `--ambient`. `prefers-reduced-motion` sets the default
on first run. Alarm state transitions ignore all of this and render
instantly by construction.
