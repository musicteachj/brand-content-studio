// The post caption half of the "LinkedIn Post" objective. The caption streams in
// live (the typing effect, with aria-live), then becomes an editable textarea you
// can tweak and copy — the copy you paste into LinkedIn alongside the card. Edits
// are local (paste-ready); they are not persisted back to the generation.
import { useState } from "react";
import { Check, Copy, Type } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { StreamAnnouncer } from "@/features/generate/StreamAnnouncer";

interface Props {
  status: "idle" | "streaming" | "done" | "error";
  streamingText: string;
  value: string;
  onChange: (v: string) => void;
  error: string | null;
}

export function PostCaptionPanel({ status, streamingText, value, onChange, error }: Props) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-5 shadow-light">
      <StreamAnnouncer status={status} label="Caption" />
      <div className="mb-3 flex items-center gap-1.5">
        <Type className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          Post caption
        </span>
      </div>

      {status === "idle" && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          Your LinkedIn caption will appear here — the copy to post with the card.
        </p>
      )}

      {status === "error" && (
        <p role="alert" className="py-6 text-sm text-destructive">
          {error ?? "Generation failed."}
        </p>
      )}

      {status === "streaming" && (
        <div
          aria-busy="true"
          className="min-h-[160px] whitespace-pre-wrap text-[15px] leading-relaxed text-foreground"
        >
          {streamingText}
          <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-accent align-middle" />
        </div>
      )}

      {status === "done" && (
        <div className="flex flex-col gap-3">
          <Textarea
            aria-label="Post caption"
            rows={9}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="text-[15px] leading-relaxed"
          />
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              {value.length} chars
            </span>
            <Button variant="ghost" size="sm" onClick={copy}>
              {copied ? (
                <Check className="h-4 w-4 text-success" aria-hidden />
              ) : (
                <Copy className="h-4 w-4" aria-hidden />
              )}
              {copied ? "Copied" : "Copy caption"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
