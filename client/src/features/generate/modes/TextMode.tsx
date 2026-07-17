import { useState } from "react";
import { Check, Copy, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ControlsPanel } from "@/features/generate/ControlsPanel";
import { RetrievalDebugPanel } from "@/features/generate/RetrievalDebugPanel";
import { StreamAnnouncer } from "@/features/generate/StreamAnnouncer";
import { useTextGeneration } from "@/features/generate/useTextGeneration";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import type { Length, Tone } from "@/types";

export function TextMode() {
  const { workspaceId } = useActiveWorkspace();
  const [brief, setBrief] = useState("");
  const [tone, setTone] = useState<Tone>("default");
  const [length, setLength] = useState<Length>("medium");
  const gen = useTextGeneration(workspaceId);
  const isStreaming = gen.status === "streaming";

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <div className="lg:sticky lg:top-6 lg:self-start">
        <ControlsPanel
          brief={brief}
          setBrief={setBrief}
          tone={tone}
          setTone={setTone}
          length={length}
          setLength={setLength}
          isStreaming={isStreaming}
          onGenerate={() => gen.generate({ brief, tone, length })}
          onStop={gen.stop}
        />
      </div>
      <div className="flex flex-col gap-6">
        <PostOutput status={gen.status} text={gen.text} error={gen.error} />
        <RetrievalDebugPanel retrieval={gen.retrieval} />
      </div>
    </div>
  );
}

function PostOutput({
  status,
  text,
  error,
}: {
  status: "idle" | "streaming" | "done" | "error";
  text: string;
  error: string | null;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="rounded-xl bg-preview-bg p-5 sm:p-8">
      <StreamAnnouncer status={status} label="Post" chars={text.length} />
      <div className="relative mx-auto w-full max-w-xl rounded-xl border border-border bg-surface p-6 shadow-preview sm:p-8">
        {status === "idle" && (
          <div className="flex min-h-[220px] flex-col items-center justify-center text-center">
            <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-surface-variant text-muted-foreground">
              <Sparkles className="h-5 w-5" aria-hidden />
            </span>
            <p className="mt-4 text-sm font-medium text-foreground">Your post will appear here</p>
            <p className="mt-1 max-w-xs text-sm text-muted-foreground">
              Enter a brief and generate — tokens stream in live, on-brand.
            </p>
          </div>
        )}

        {status === "error" && (
          <p role="alert" className="min-h-[120px] text-sm text-destructive">
            {error ?? "Generation failed."}
          </p>
        )}

        {(status === "streaming" || status === "done") && (
          <>
            <div
              aria-busy={status === "streaming"}
              className="whitespace-pre-wrap text-[15px] leading-relaxed text-foreground"
            >
              {text}
              {status === "streaming" && (
                <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-accent align-middle" />
              )}
            </div>
            {status === "done" && (
              <div className="mt-5 flex items-center justify-between border-t border-border pt-4">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  {text.length} chars
                </span>
                <Button variant="ghost" size="sm" onClick={copy}>
                  {copied ? (
                    <Check className="h-4 w-4 text-success" aria-hidden />
                  ) : (
                    <Copy className="h-4 w-4" aria-hidden />
                  )}
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
