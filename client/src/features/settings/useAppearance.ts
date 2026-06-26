import { useEffect } from "react";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { applyAccentTint } from "@/lib/colorTint";
import { useSettingsStore } from "@/stores/settings";

/** Applies the user's appearance settings to the document: the theme (light /
 *  dark / system, toggling the `.dark` class) and the optional workspace
 *  brand-color accent tint (DESIGN §4). Mount once, high in the app tree. */
export function useAppearance(): void {
  const theme = useSettingsStore((s) => s.theme);
  const brandTint = useSettingsStore((s) => s.brandTint);
  const { workspace } = useActiveWorkspace();

  // Theme: explicit light/dark, or follow the OS when "system".
  useEffect(() => {
    const root = document.documentElement;
    const apply = (dark: boolean) => root.classList.toggle("dark", dark);
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      apply(mq.matches);
      const onChange = (e: MediaQueryListEvent) => apply(e.matches);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    }
    apply(theme === "dark");
  }, [theme]);

  // Accent tint: the active workspace's primary brand color when enabled, else
  // Folio's own magenta. Cosmetic only — never bleeds into semantic tokens.
  const primaryHex = workspace?.brand_profile.colors.find((c) => c.role === "primary")?.hex ?? null;
  useEffect(() => {
    applyAccentTint(brandTint ? primaryHex : null);
    return () => applyAccentTint(null);
  }, [brandTint, primaryHex]);
}
