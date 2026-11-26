import { Check, Sparkles, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { TemplatePicker } from "@/features/generate/TemplatePicker";
import { cn } from "@/lib/utils";
import type { BrandProfile, CardPreset, CardTemplate, Tone } from "@/types";

const TONES: { value: Tone; label: string }[] = [
  { value: "default", label: "Brand default" },
  { value: "confident", label: "Confident" },
  { value: "warm", label: "Warm" },
  { value: "technical", label: "Technical" },
  { value: "provocative", label: "Provocative" },
];

interface Props {
  brand: BrandProfile;
  brief: string;
  setBrief: (v: string) => void;
  tone: Tone;
  setTone: (v: Tone) => void;
  template: CardTemplate | null;
  setTemplate: (v: CardTemplate) => void;
  presets: CardPreset[];
  onApplyPreset: (p: CardPreset) => void;
  isStreaming: boolean;
  hasGenerated: boolean;
  onGenerate: () => void;
  onStop: () => void;
}

/** A numbered step marker: completed steps show a check, the current step is
 *  outlined in accent. Reuses Folio's mono eyebrow style so the card flow reads as
 *  a guided sequence without a heavyweight wizard (DESIGN §4). */
function StepHeader({
  n,
  label,
  done,
  active,
}: {
  n: number;
  label: string;
  done: boolean;
  active: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-2xs font-semibold",
          done
            ? "bg-accent text-accent-foreground"
            : active
              ? "border border-accent text-accent"
              : "bg-surface-variant text-muted-foreground",
        )}
      >
        {done ? <Check className="h-3 w-3" aria-hidden /> : n}
      </span>
      <span className="eyebrow text-[11px]">{label}</span>
    </div>
  );
}

export function CardControlsPanel({
  brand,
  brief,
  setBrief,
  tone,
  setTone,
  template,
  setTemplate,
  presets,
  onApplyPreset,
  isStreaming,
  hasGenerated,
  onGenerate,
  onStop,
}: Props) {
  const templateOk = template !== null;
  const briefOk = brief.trim().length >= 3;
  const canGenerate = briefOk && templateOk && !isStreaming;
  // A ready brief with no layout: say why Generate is disabled (QA-08).
  const needsLayout = briefOk && !templateOk && !isStreaming;

  return (
    <div className="flex flex-col gap-6 rounded-lg border border-border bg-surface p-5 shadow-light">
      {presets.length > 0 && (
        <div>
          <Label htmlFor="card-preset">Preset</Label>
          <Select
            id="card-preset"
            value=""
            disabled={isStreaming}
            onChange={(e) => {
              const p = presets.find((x) => x.id === e.target.value);
              if (p) onApplyPreset(p);
            }}
          >
            <option value="">Apply a saved preset…</option>
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <p className="mt-1.5 text-xs text-muted-foreground">
            Sets the layout now; the accent applies once the card generates.
          </p>
        </div>
      )}

      <div>
        <StepHeader n={1} label="Template" done={templateOk} active={!templateOk} />
        <p className="mb-2.5 mt-2 text-xs text-muted-foreground">
          Pick a layout. This is the card you’ll generate.
        </p>
        <TemplatePicker
          brand={brand}
          value={template}
          onChange={setTemplate}
          disabled={isStreaming}
        />
      </div>

      <div>
        <StepHeader n={2} label="Brief" done={briefOk} active={templateOk && !briefOk} />
        <div className="mt-2.5">
          <Label htmlFor="card-brief">Your brief</Label>
          <Textarea
            id="card-brief"
            rows={4}
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder="e.g. Why specifying low-carbon materials early cuts the most embodied carbon."
          />
          <p className="mt-1.5 text-xs text-muted-foreground">
            Retrieval pulls the on-brand material; copy is written to fit the layout.
          </p>
        </div>
        <div className="mt-3">
          <Label htmlFor="card-tone">Tone</Label>
          <Select id="card-tone" value={tone} onChange={(e) => setTone(e.target.value as Tone)}>
            {TONES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div>
        {isStreaming ? (
          <Button variant="secondary" className="w-full" onClick={onStop}>
            <Square className="h-4 w-4" aria-hidden />
            Stop
          </Button>
        ) : (
          <Button
            className="w-full"
            onClick={onGenerate}
            disabled={!canGenerate}
            aria-describedby={needsLayout ? "card-layout-hint" : undefined}
          >
            <Sparkles className="h-4 w-4" aria-hidden />
            {hasGenerated ? "Regenerate card" : "Generate card"}
          </Button>
        )}
        {needsLayout ? (
          <p id="card-layout-hint" className="mt-2.5 text-center text-xs text-muted-foreground">
            Pick a layout above to generate.
          </p>
        ) : (
          !hasGenerated &&
          !isStreaming && (
            <p className="mt-2.5 text-center text-xs text-muted-foreground">
              Then add an image and export it, on the card to the right.
            </p>
          )
        )}
      </div>
    </div>
  );
}
