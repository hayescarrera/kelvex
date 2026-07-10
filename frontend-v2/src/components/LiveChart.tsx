/**
 * uPlot wrapper: canvas rendering, 100k+ points without jank, live tailing,
 * drag-to-zoom (uPlot native), double-click to reset. Chart style
 * (line/step/area) follows user prefs. Respects units and stale styling.
 */
import { useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { usePrefs } from "../state/prefs";
import { convert, type Kind } from "../lib/format";

export function LiveChart({ series, kind, height = 220, label, stale = false }: {
  series: [number[], number[]];
  kind: Kind;
  height?: number;
  label: string;
  stale?: boolean;
}) {
  const prefs = usePrefs();
  const ref = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const zoomed = useRef(false);

  const data = useMemo<uPlot.AlignedData>(() => {
    const [t, v] = series;
    return [t, v.map((x) => convert(x, kind, prefs))];
  }, [series, kind, prefs.tempUnit, prefs.pressureUnit, prefs.massUnit]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ref.current) return;
    const style = getComputedStyle(document.documentElement);
    const accent = style.getPropertyValue("--accent").trim() || "#3b82f6";
    const gridColor = style.getPropertyValue("--chart-grid").trim() || "rgba(150,150,150,.12)";
    const inkColor = style.getPropertyValue("--ink-3").trim() || "#888";
    const staleColor = style.getPropertyValue("--status-stale").trim() || "#8b93a7";
    const lineColor = stale ? staleColor : accent;

    const paths =
      prefs.chartStyle === "step"
        ? uPlot.paths.stepped!({ align: 1 })
        : uPlot.paths.linear!();

    const opts: uPlot.Options = {
      width: ref.current.clientWidth,
      height,
      pxAlign: 0,
      cursor: { drag: { x: true, y: false } },
      legend: { show: false },
      scales: { x: { time: true } },
      axes: [
        { stroke: inkColor, grid: { stroke: gridColor }, ticks: { show: false }, font: "11px JetBrains Mono" },
        { stroke: inkColor, grid: { stroke: gridColor }, ticks: { show: false }, font: "11px JetBrains Mono", size: 52 },
      ],
      series: [
        {},
        {
          label,
          stroke: lineColor,
          width: 1.6,
          paths,
          fill: prefs.chartStyle === "area"
            ? `${lineColor}22`
            : undefined,
          points: { show: false },
        },
      ],
      hooks: {
        setSelect: [(u) => { if (u.select.width > 0) zoomed.current = true; }],
      },
    };

    const p = new uPlot(opts, data, ref.current);
    plot.current = p;

    const el = ref.current;
    const onDblClick = () => { zoomed.current = false; };
    el.addEventListener("dblclick", onDblClick);

    const ro = new ResizeObserver(() => {
      if (ref.current) p.setSize({ width: ref.current.clientWidth, height });
    });
    ro.observe(el);

    return () => { ro.disconnect(); el.removeEventListener("dblclick", onDblClick); p.destroy(); plot.current = null; };
    // Recreate on style-affecting pref changes:
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs.chartStyle, prefs.theme, prefs.accent, height, stale]);

  // Live tail: update data in place unless the user has zoomed in.
  useEffect(() => {
    if (plot.current && !zoomed.current) plot.current.setData(data);
  }, [data]);

  return <div ref={ref} role="img" aria-label={`${label} chart`} />;
}
