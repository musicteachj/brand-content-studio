import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { cn } from "@/lib/utils";
import { useSettingsStore, type ThemePref } from "@/stores/settings";
import type { BrandProfile } from "@/types";

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

      {brand && (
        <Section
          title="Brand identity"
          hint={`Read-only — from ${workspace?.name ?? "the workspace"}.`}
        >
          <BrandIdentity brand={brand} />
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3 animate-fade-in-up">
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

function BrandIdentity({ brand }: { brand: BrandProfile }) {
  const fonts = [
    ["Heading", brand.fonts.heading],
    ["Body", brand.fonts.body],
    ["Mono", brand.fonts.mono],
  ].filter(([, v]) => v) as [string, string][];

  return (
    <div className="flex flex-col gap-5 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex flex-col gap-2.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Colors
        </span>
        <div className="flex flex-wrap gap-3">
          {brand.colors.map((c) => (
            <div key={`${c.hex}-${c.name}`} className="flex items-center gap-2">
              <span
                className="h-7 w-7 rounded-md border border-border"
                style={{ backgroundColor: c.hex }}
                aria-hidden
              />
              <div className="flex flex-col leading-tight">
                <span className="text-xs font-medium text-foreground">{c.name}</span>
                <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                  {c.hex}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {fonts.length > 0 && (
        <div className="flex flex-col gap-2.5 border-t border-border pt-4">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Typography
          </span>
          <dl className="flex flex-col gap-1.5">
            {fonts.map(([role, name]) => (
              <div key={role} className="flex items-baseline justify-between gap-4">
                <dt className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                  {role}
                </dt>
                <dd className="text-sm text-foreground">{name}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
