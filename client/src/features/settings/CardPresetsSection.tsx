import { useState } from "react";
import { LayoutTemplate, Plus, Trash2 } from "lucide-react";
import { useAddCardPreset, useRemoveCardPreset } from "@/api/workspaces";
import { TemplatePicker } from "@/features/generate/TemplatePicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useRovingRadio } from "@/lib/useRovingRadio";
import { useAuthStore } from "@/stores/auth";
import type { CardTemplate, Workspace } from "@/types";

const MAX_PRESETS = 8;
const TEMPLATE_LABEL: Record<CardTemplate, string> = {
  "photo-led": "Photo-led",
  statement: "Statement",
  quote: "Quote",
};

/** Settings → Card presets. Save a named card *look* (template + accent) to reuse
 *  from the card generate flow. Fonts/colors are workspace-global, so a preset is
 *  just the two per-card knobs. Demo-blocked; capped (Phase 5 PR-B). */
export function CardPresetsSection({ workspace }: { workspace: Workspace }) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const brand = workspace.brand_profile;
  const add = useAddCardPreset(workspace.id);
  const remove = useRemoveCardPreset(workspace.id);
  const [name, setName] = useState("");
  const [template, setTemplate] = useState<CardTemplate>("photo-led");
  const [accentHex, setAccentHex] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const presets = brand.card_presets ?? [];
  const atCap = presets.length >= MAX_PRESETS;
  // Accent radiogroup options: index 0 = brand default (null), then each palette color.
  const accentOptions: (string | null)[] = [null, ...brand.colors.map((c) => c.hex)];
  const { radioProps: accentRadioProps } = useRovingRadio(
    accentOptions.length,
    accentOptions.findIndex((hex) => (hex?.toLowerCase() ?? null) === (accentHex?.toLowerCase() ?? null)),
    (i) => setAccentHex(accentOptions[i]),
  );

  async function onAdd() {
    if (!name.trim()) {
      setError("Give the preset a name first.");
      return;
    }
    setError(null);
    try {
      await add.mutateAsync({ name: name.trim(), template_id: template, accent_hex: accentHex });
      setName("");
      setAccentHex(null);
    } catch {
      setError("Couldn’t save that preset. Use a unique name (max 8 presets).");
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-light">
      <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        Card presets · {presets.length} of {MAX_PRESETS}
      </span>
      <p className="text-sm text-muted-foreground">
        Save a named look — a layout plus an accent — to apply in one click when generating a card.
      </p>

      {!isDemo && !atCap && (
        <div className="flex flex-col gap-3 rounded-lg border border-border p-3">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Preset name (e.g. Bold quote)"
            className="h-8 text-sm"
          />
          <TemplatePicker
            brand={brand}
            value={template}
            onChange={setTemplate}
            accentHex={accentHex}
          />
          <div
            className="flex flex-wrap items-center gap-2"
            role="radiogroup"
            aria-label="Preset accent color"
          >
            <button
              type="button"
              role="radio"
              aria-checked={accentHex === null}
              aria-label="Brand default accent"
              title="Brand default"
              onClick={() => setAccentHex(null)}
              {...accentRadioProps(0)}
              className={cn(
                "h-7 rounded-full border px-3 text-xs transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                accentHex === null
                  ? "border-2 border-foreground"
                  : "border-border hover:shadow-light",
              )}
            >
              Default
            </button>
            {brand.colors.map((color, i) => {
              const selected = color.hex.toLowerCase() === accentHex?.toLowerCase();
              return (
                <button
                  key={`${color.hex}-${color.name}`}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  aria-label={`${color.name} accent`}
                  title={color.name}
                  onClick={() => setAccentHex(color.hex)}
                  {...accentRadioProps(i + 1)}
                  className={cn(
                    "h-7 w-7 rounded-full border transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    selected
                      ? "border-2 border-foreground shadow-light"
                      : "border-border hover:shadow-light",
                  )}
                  style={{ backgroundColor: color.hex }}
                />
              );
            })}
          </div>
          {error && <span className="text-xs text-destructive">{error}</span>}
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={onAdd}
            loading={add.isPending}
            className="self-start"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Save preset
          </Button>
        </div>
      )}
      {atCap && !isDemo && (
        <span className="text-xs text-muted-foreground">
          You’ve reached the {MAX_PRESETS}-preset limit — delete one to add another.
        </span>
      )}

      {presets.length === 0 ? (
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          <LayoutTemplate className="h-4 w-4" aria-hidden />
          No card presets yet.
        </span>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {presets.map((p) => (
            <li
              key={p.id}
              className="flex items-center justify-between rounded-md border border-border px-3 py-2"
            >
              <span className="flex items-center gap-2.5 text-sm text-foreground">
                <span
                  className="h-4 w-4 shrink-0 rounded-full border border-border"
                  style={{ backgroundColor: p.accent_hex ?? "transparent" }}
                  aria-hidden
                />
                <span className="font-medium">{p.name}</span>
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                  {TEMPLATE_LABEL[p.template_id]}
                </span>
              </span>
              {!isDemo && (
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  onClick={() => remove.mutate(p.id)}
                  loading={remove.isPending}
                  aria-label={`Remove ${p.name}`}
                  className="h-7 w-7 hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
