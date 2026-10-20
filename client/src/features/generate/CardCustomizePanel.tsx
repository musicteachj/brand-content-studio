import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TemplatePicker } from "@/features/generate/TemplatePicker";
import { cardColors } from "@/features/generate/cards/cardElement";
import { cn } from "@/lib/utils";
import { useRovingRadio } from "@/lib/useRovingRadio";
import type { BrandProfile, CardTemplate } from "@/types";

interface Props {
  brand: BrandProfile;
  template: CardTemplate;
  accentHex: string | null;
  dirty: boolean;
  saving: boolean;
  saveError: string | null;
  onTemplate: (t: CardTemplate) => void;
  onAccent: (hex: string) => void;
  onSave: () => void;
  onDiscard: () => void;
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5">
      <span className="eyebrow">{label}</span>
      {children}
    </div>
  );
}

/** Quiet post-generation customization (Phase 1.5): swap the layout and pick the
 *  accent from the brand palette — all client-side, re-rendered live in the
 *  preview, persisted only on Save (PATCH, never a `/generate` call). The preview
 *  stays the hero; this panel recedes beneath it. */
export function CardCustomizePanel({
  brand,
  template,
  accentHex,
  dirty,
  saving,
  saveError,
  onTemplate,
  onAccent,
  onSave,
  onDiscard,
}: Props) {
  // The accent actually in effect (per-card override, else the brand default) —
  // so the matching swatch reads as selected even before the user picks one.
  const effectiveAccent = cardColors(brand, accentHex).accent.toLowerCase();
  const { radioProps: accentRadioProps } = useRovingRadio(
    brand.colors.length,
    brand.colors.findIndex((c) => c.hex.toLowerCase() === effectiveAccent),
    (i) => onAccent(brand.colors[i].hex),
  );

  return (
    <div className="flex flex-col gap-5 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Customize</h2>
        {dirty && (
          <span className="font-mono text-2xs uppercase tracking-eyebrow text-warning">
            Unsaved
          </span>
        )}
      </div>

      <Section label="Layout">
        <TemplatePicker
          brand={brand}
          value={template}
          onChange={onTemplate}
          accentHex={accentHex}
        />
      </Section>

      <Section label="Accent">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Card accent color">
          {brand.colors.map((color, index) => {
            const selected = color.hex.toLowerCase() === effectiveAccent;
            return (
              <button
                key={`${color.hex}-${color.name}`}
                type="button"
                role="radio"
                aria-checked={selected}
                aria-label={`${color.name} accent`}
                title={color.name}
                onClick={() => onAccent(color.hex)}
                {...accentRadioProps(index)}
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-full border transition-shadow focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
                  selected
                    ? "border-2 border-foreground shadow-light"
                    : "border-border hover:shadow-light",
                )}
                style={{ backgroundColor: color.hex }}
              >
                {selected && (
                  <Check
                    className="h-4 w-4"
                    style={{ color: contrastInk(color.hex) }}
                    aria-hidden
                  />
                )}
              </button>
            );
          })}
        </div>
      </Section>

      {dirty && (
        <div className="flex flex-col gap-2 border-t border-border pt-4">
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" onClick={onDiscard} disabled={saving}>
              Discard
            </Button>
            <Button onClick={onSave} loading={saving}>
              Save changes
            </Button>
          </div>
          {saveError && (
            <p role="alert" className="text-xs text-destructive">
              {saveError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Pick a readable check color (black/white) for the swatch by luminance. */
function contrastInk(hex: string): string {
  const h = hex.replace("#", "");
  const full =
    h.length === 3
      ? h
          .split("")
          .map((x) => x + x)
          .join("")
      : h;
  const r = parseInt(full.slice(0, 2), 16) || 0;
  const g = parseInt(full.slice(2, 4), 16) || 0;
  const b = parseInt(full.slice(4, 6), 16) || 0;
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? "#1A1D21" : "#FFFFFF";
}
