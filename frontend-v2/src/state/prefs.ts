/**
 * User preferences — persisted per user.
 *
 * In production this hydrates from GET /auth/me/preferences and writes back
 * with a debounced PATCH; the localStorage persistence here is the demo
 * stand-in with an identical shape. Mode/theme/density/motion apply as
 * attributes on <html> so switching is a token swap — no reload, no remount.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Density = "compact" | "comfortable" | "spacious";
export type Motion = "full" | "reduced" | "none";
export type Theme = "dark" | "light" | "system";
export type Accent = "blue" | "cyan" | "violet" | "teal";
export type TempUnit = "F" | "C";
export type PressureUnit = "psi" | "kPa";
export type MassUnit = "lb" | "kg";
export type TzMode = "site" | "user";
export type ChartStyle = "line" | "step" | "area";

export interface Prefs {
  density: Density;
  motion: Motion;
  theme: Theme;
  accent: Accent;
  tempUnit: TempUnit;
  pressureUnit: PressureUnit;
  massUnit: MassUnit;
  tzMode: TzMode;
  defaultLanding: string;
  defaultSiteId: string | null;
  defaultRangeHours: number;
  chartStyle: ChartStyle;
  tourDone: boolean;
}

interface PrefsStore extends Prefs {
  set: <K extends keyof Prefs>(key: K, value: Prefs[K]) => void;
}

const systemPrefersReduced = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const defaults: Prefs = {
  density: "comfortable",
  motion: systemPrefersReduced() ? "reduced" : "full",
  theme: "light",
  accent: "blue",
  tempUnit: "F",
  pressureUnit: "psi",
  massUnit: "lb",
  tzMode: "site",
  defaultLanding: "/",
  defaultSiteId: null,
  defaultRangeHours: 24,
  chartStyle: "line",
  tourDone: false,
};

export const usePrefs = create<PrefsStore>()(
  persist(
    (set) => ({
      ...defaults,
      set: (key, value) => set({ [key]: value } as Partial<Prefs>),
    }),
    { name: "kelvex-prefs-v2" },
  ),
);

/** Reflect prefs onto <html> so CSS tokens react instantly. */
export function applyPrefsToDocument(p: Prefs) {
  const el = document.documentElement;
  el.dataset.density = p.density;
  el.dataset.motion = p.motion;
  el.dataset.accent = p.accent;
  const theme =
    p.theme === "system"
      ? window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark"
      : p.theme;
  el.dataset.theme = theme;
}

// Keep the document in sync from anywhere prefs change.
usePrefs.subscribe((state) => applyPrefsToDocument(state));
