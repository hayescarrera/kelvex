# Kelvex Ops — Design Spec (v3, category-standard)

Modeled on the vertical-SaaS operator dashboards this market already trusts
(Axiom Cloud's single pane of glass; Samsara-class visual language): light
theme, white cards on a gray canvas, blue primary, and prioritization as
the core design idea — health scores and ranked queues over decoration.

## Visual language

- **Light theme default** (`data-theme` supports dark for overnight use)
- Canvas `#f6f7f9`, white cards, 1px `#e6e9ef` borders, 10px radii, soft
  two-layer shadows
- Inter for UI (global tabular numerals), Space Grotesk for headings and
  display numbers, JetBrains Mono for telemetry/IDs
- Status colors (red/amber/green/blue/slate) reserved exclusively for
  state; user accent choice can never repaint them

## Signature constructs (the Axiom-class patterns)

1. **Site health score (0–100)** — rolls up alarms, stale sensors, leak
   clocks, gateway state; ring gauge on dashboard + site header
2. **Needs-attention queue** — every urgent thing (alarms, repair
   deadlines, failure risk) in one list, ranked; work top to bottom
3. **Compressors ranked by failure probability** — highest risk floats to
   the top, red/amber/green probability bars
4. **Work-order lifecycle chips** — alert → dispatched → in progress →
   closed, advanced inline from the alarm inbox
5. **KPI cards with period deltas** — ▲/▼ movement vs prior period

## Kept from v2 (substance, not style)

Provenance popovers on every number · stale = desaturated + timestamped +
labeled · repair clock follows the asset everywhere · critical states
render with transitions disabled in CSS · icon+text+color for all status ·
⌘K palette · keyboard triage (J/K/A/S/N) · HelpTip compliance explainers ·
"What can I do here?" per screen · empty-states-as-tutorial · uPlot canvas
charts with live tail and drag-zoom · mock engine for cold demos ·
unit/timezone/density/motion preferences.

## Screens

Dashboard · Site detail · Asset detail · Alarm inbox · Leak events ·
Refrigerant ledger · Compliance & reporting (inspector-exact export
preview) · Edge agents · Admin · Preferences.
