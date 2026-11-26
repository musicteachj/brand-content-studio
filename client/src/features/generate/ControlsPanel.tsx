import { Sparkles, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { Length, Tone } from "@/types";

const TONES: { value: Tone; label: string }[] = [
  { value: "default", label: "Brand default" },
  { value: "confident", label: "Confident" },
  { value: "warm", label: "Warm" },
  { value: "technical", label: "Technical" },
  { value: "provocative", label: "Provocative" },
];

const LENGTHS: { value: Length; label: string }[] = [
  { value: "short", label: "Short" },
  { value: "medium", label: "Medium" },
  { value: "long", label: "Long" },
];

interface Props {
  brief: string;
  setBrief: (v: string) => void;
  tone: Tone;
  setTone: (v: Tone) => void;
  length: Length;
  setLength: (v: Length) => void;
  onGenerate: () => void;
  onStop: () => void;
  isStreaming: boolean;
}

export function ControlsPanel({
  brief,
  setBrief,
  tone,
  setTone,
  length,
  setLength,
  onGenerate,
  onStop,
  isStreaming,
}: Props) {
  const canGenerate = brief.trim().length >= 3 && !isStreaming;
  return (
    <div className="rounded-lg border border-border bg-surface p-5 shadow-light">
      <div>
        <Label htmlFor="brief">Brief</Label>
        <Textarea
          id="brief"
          rows={5}
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="e.g. A post on why early-stage material decisions cut embodied carbon the most."
        />
        <p className="mt-1.5 text-xs text-muted-foreground">
          Describe the post you want. Retrieval pulls the on-brand material automatically.
        </p>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="tone">Tone</Label>
          <Select id="tone" value={tone} onChange={(e) => setTone(e.target.value as Tone)}>
            {TONES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="length">Length</Label>
          <Select id="length" value={length} onChange={(e) => setLength(e.target.value as Length)}>
            {LENGTHS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="mt-5">
        {isStreaming ? (
          <Button variant="secondary" className="w-full" onClick={onStop}>
            <Square className="h-4 w-4" aria-hidden />
            Stop
          </Button>
        ) : (
          <Button className="w-full" onClick={onGenerate} disabled={!canGenerate}>
            <Sparkles className="h-4 w-4" aria-hidden />
            Generate post
          </Button>
        )}
      </div>
    </div>
  );
}
