import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemePref = "light" | "dark" | "system";

/** App appearance preferences (Phase 1.5 Settings). Light-first per DESIGN §0;
 *  dark is a user preference, not the default. `brandTint` controls the optional
 *  workspace brand-color UI tint (DESIGN §4) — on by default so the app wears the
 *  active brand, but a user can keep Folio's own identity. */
interface SettingsState {
  theme: ThemePref;
  brandTint: boolean;
  setTheme: (t: ThemePref) => void;
  setBrandTint: (on: boolean) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      theme: "light",
      brandTint: true,
      setTheme: (theme) => set({ theme }),
      setBrandTint: (brandTint) => set({ brandTint }),
    }),
    { name: "folio-settings" },
  ),
);
