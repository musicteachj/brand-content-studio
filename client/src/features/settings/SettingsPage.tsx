import { useEffect } from "react";
import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { useLocation } from "react-router-dom";
import { DemoNotice } from "@/components/DemoNotice";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore, type ThemePref } from "@/stores/settings";
import { BrandIdentityEditor } from "./BrandIdentityEditor";
import { BrandImagesSection } from "./BrandImagesSection";
import { ExemplarsSection } from "./ExemplarsSection";
import { WorkspacesSection } from "./WorkspacesSection";

const THEMES: { value: ThemePref; label: string; icon: LucideIcon }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

/** Quiet Settings page (Phase 1.5): appearance (theme + the optional workspace
 *  brand-color UI tint) and a read-only view of the active workspace's brand
 *  identity. Intentionally minimal — no account or destructive controls. */
export function SettingsPage() {
  const { workspace } = useActiveWorkspace();
  const theme = useSettingsStore((s) => s.theme);
  const setTheme = useSettingsStore((s) => s.setTheme);
  const brandTint = useSettingsStore((s) => s.brandTint);
  const setBrandTint = useSettingsStore((s) => s.setBrandTint);
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const { hash } = useLocation();

  // Deep-link from the workspace switcher's "Manage workspaces" (/settings#workspaces).
  useEffect(() => {
    if (!hash) return;
    document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
  }, [hash]);

  const brand = workspace?.brand_profile ?? null;
  const primary = brand?.colors.find((c) => c.role === "primary")?.hex ?? null;

  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <header className="animate-fade-in-up">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
          Settings
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-0.01em] text-foreground">
          Appearance
        </h1>
      </header>

      {isDemo && (
        <DemoNotice message="You're exploring as a demo — workspace management, brand identity, and example cards are read-only so the seeded Verdure workspace stays intact. Theme and appearance still work, and you can still generate posts, cards, and documents." />
      )}

      <Section title="Theme" hint="Light is the studio default; pick what suits you.">
        <div
          className="inline-flex gap-1 rounded-md border border-border bg-surface p-1"
          role="radiogroup"
          aria-label="Theme"
        >
          {THEMES.map(({ value, label, icon: Icon }) => {
            const active = theme === value;
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setTheme(value)}
                className={cn(
                  "flex items-center gap-1.5 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active
                    ? "bg-surface-variant text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label}
              </button>
            );
          })}
        </div>
      </Section>

      <Section
        title="Brand color tint"
        hint="Tint active nav and selected states with the workspace’s primary brand color. Cosmetic only — it never changes status colors."
      >
        <div className="flex items-center gap-3">
          <Toggle
            checked={brandTint}
            onChange={setBrandTint}
            label="Use the workspace brand color for accents"
          />
          {primary && (
            <span className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
              <span
                className="h-4 w-4 rounded-full border border-border"
                style={{ backgroundColor: primary }}
                aria-hidden
              />
              {brandTint ? "Brand" : "Folio"}
            </span>
          )}
        </div>
      </Section>

      <Section
        id="workspaces"
        title="Workspaces"
        hint="Switch from the top bar; rename or delete here. Each workspace is an isolated brand."
      >
        <WorkspacesSection />
      </Section>

      {workspace && (
        <Section
          title="Brand identity"
          hint={`The palette, fonts, voice, and logo for ${workspace.name}. These drive generated cards — not the app chrome.`}
        >
          <BrandIdentityEditor workspace={workspace} />
        </Section>
      )}

      {workspace && (
        <Section
          title="Example cards"
          hint="Teach the studio your card style by example — uploads steer generated copy."
        >
          <ExemplarsSection workspace={workspace} />
        </Section>
      )}

      {workspace && (
        <Section
          title="Brand images"
          hint="Your own images, saved once and reusable as card pictures from the image picker."
        >
          <BrandImagesSection workspace={workspace} />
        </Section>
      )}
    </div>
  );
}

function Section({
  id,
  title,
  hint,
  children,
}: {
  id?: string;
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="flex flex-col gap-3 animate-fade-in-up scroll-mt-6">
      <div>
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{hint}</p>
      </div>
      {children}
    </section>
  );
}

/** Accessible pill switch built from tokens (no Switch primitive in the kit). */
function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        checked ? "bg-accent" : "bg-surface-variant",
      )}
    >
      <span
        className={cn(
          "inline-block h-5 w-5 transform rounded-full bg-surface shadow-light transition-transform",
          checked ? "translate-x-[22px]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}
