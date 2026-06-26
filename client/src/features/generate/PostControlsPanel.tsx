import { Sparkles, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { TemplatePicker } from "@/features/generate/TemplatePicker";
import type { BrandProfile, CardTemplate, Tone } from "@/types";

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
  template: CardTemplate;
  setTemplate: (v: CardTemplate) => void;
  isStreaming: boolean;
  hasGenerated: boolean;
  onGenerate: () => void;
  onStop: () => void;
}

/** Controls for the "LinkedIn Post" objective: one brief yields the post caption
 *  AND the matching card. The brief drives both; the template chooses the card. */
export function PostControlsPanel({
  brand,
  brief,
  setBrief,
  tone,
  setTone,
  template,
  setTemplate,
  isStreaming,
  hasGenerated,
  onGenerate,
  onStop,
}: Props) {
  const canGenerate = brief.trim().length >= 3 && !isStreaming;

  return (
    <div className="flex flex-col gap-5 rounded-lg border border-border bg-surface p-5 shadow-light">
      <div>
        <Label htmlFor="post-brief">Brief</Label>
        <Textarea
          id="post-brief"
          rows={5}
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="e.g. Why specifying low-carbon materials early cuts the most embodied carbon."
        />
        <p className="mt-1.5 text-xs text-muted-foreground">
          You’ll get a full post caption <strong>and</strong> a matching card — both on-brand, from
          one brief.
        </p>
      </div>

      <div>
        <Label htmlFor="post-tone">Tone</Label>
        <Select id="post-tone" value={tone} onChange={(e) => setTone(e.target.value as Tone)}>
          {TONES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </Select>
      </div>

      <div>
        <Label>Card layout</Label>
        <div className="mt-1.5">
          <TemplatePicker
            brand={brand}
            value={template}
            onChange={setTemplate}
            disabled={isStreaming}
          />
        </div>
      </div>

      <div>
        {isStreaming ? (
          <Button variant="secondary" className="w-full" onClick={onStop}>
            <Square className="h-4 w-4" aria-hidden />
            Stop
          </Button>
        ) : (
          <Button className="w-full" onClick={onGenerate} disabled={!canGenerate}>
            <Sparkles className="h-4 w-4" aria-hidden />
            {hasGenerated ? "Regenerate post" : "Generate post"}
          </Button>
        )}
      </div>
    </div>
  );
}
