import type { Theme } from "./types";

const KEY = "textchef.theme";

export function savedTheme(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

export function saveTheme(name: string): void {
  try { localStorage.setItem(KEY, name); } catch { /* private mode */ }
}

export function prefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Write a theme's palette and fonts onto :root as CSS variables. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(theme.colors)) {
    root.style.setProperty(`--${key.replace(/_/g, "-")}`, value);
  }
  root.style.setProperty("--lift-low", theme.graph.lift_low);
  root.style.setProperty("--lift-high", theme.graph.lift_high);
  root.style.setProperty("--font", theme.font);
  root.style.setProperty("--font-mono", theme.font_mono);
  root.style.colorScheme = theme.scheme;
  root.dataset.theme = theme.name;
  document.title = theme.strings.title;
}
