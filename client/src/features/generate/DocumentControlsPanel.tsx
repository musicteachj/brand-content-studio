import { FileText, Sparkles, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { DocumentArchetype, Tone } from "@/types";

const TONES: { value: Tone; label: string }[] = [
  { value: "default", label: "Brand default" },
  { value: "confident", label: "Confident" },
  { value: "warm", label: "Warm" },
  { value: "technical", label: "Technical" },
  { value: "provocative", label: "Provocative" },
];

const ARCHETYPES: { value: DocumentArchetype; label: string; hint: string }[] = [
  {
    value: "one-pager",
    label: "One-pager",
    hint: "A single-page brand document, as .docx and PDF.",
  },
  {
    value: "short-deck",
    label: "Short deck",
    hint: "A tight deck of title and content slides, as .pptx.",
  },
];

interface Props {
  brief: string;
  setBrief: (v: string) => void;
  archetype: DocumentArchetype;
  setArchetype: (v: DocumentArchetype) => void;
  tone: Tone;
  setTone: (v: Tone) => void;
  onGenerate: () => void;
  onStop: () => void;
  isStreaming: boolean;
}

export function DocumentControlsPanel({
  brief,
  setBrief,
  archetype,
  setArchetype,
  tone,
  setTone,
  onGenerate,
  onStop,
  isStreaming,
}: Props) {
  const canGenerate = brief.trim().length >= 3 && !isStreaming;
  const activeHint = ARCHETYPES.find((a) => a.value === archetype)?.hint;

  return (
    <div className="rounded-lg border border-border bg-surface p-5 shadow-light">
      <div>
        <Label htmlFor="doc-format">Format</Label>
        <Select
          id="doc-format"
          value={archetype}
          onChange={(e) => setArchetype(e.target.value as DocumentArchetype)}
        >
          {ARCHETYPES.map((a) => (
            <option key={a.value} value={a.value}>
              {a.label}
            </option>
          ))}
        </Select>
        {activeHint && (
          <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            <FileText className="h-3.5 w-3.5" aria-hidden />
            {activeHint}
          </p>
        )}
      </div>

      <div className="mt-4">
        <Label htmlFor="doc-brief">Brief</Label>
        <Textarea
          id="doc-brief"
          rows={5}
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="e.g. A one-pager introducing our recycled-denim insulation to architects."
        />
        <p className="mt-1.5 text-xs text-muted-foreground">
          Describe the document you need. Retrieval pulls the on-brand material automatically.
        </p>
      </div>

      <div className="mt-4">
        <Label htmlFor="doc-tone">Tone</Label>
        <Select id="doc-tone" value={tone} onChange={(e) => setTone(e.target.value as Tone)}>
          {TONES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </Select>
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
            Generate document
          </Button>
        )}
      </div>
    </div>
  );
}
