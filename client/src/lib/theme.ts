/** Light-first theme toggle. Light is primary; dark is a saved preference (DESIGN.md §0). */
const KEY = "folio-theme";
export type Theme = "light" | "dark";

export function getTheme(): Theme {
  // Light-first (DESIGN.md §0): default to light; dark only when the user explicitly chose it.
  return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem(KEY, theme);
}

export function initTheme(): void {
  applyTheme(getTheme());
}

export function toggleTheme(): Theme {
  const next: Theme = document.documentElement.classList.contains("dark") ? "light" : "dark";
  applyTheme(next);
  return next;
}
