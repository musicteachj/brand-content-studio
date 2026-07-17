import { useState } from "react";
import { FileType, Image as ImageIcon, Megaphone, Type } from "lucide-react";
import { EmptyCorpus } from "@/features/generate/EmptyCorpus";
import { CardMode } from "@/features/generate/modes/CardMode";
import { DocumentMode } from "@/features/generate/modes/DocumentMode";
import { PostPackMode } from "@/features/generate/modes/PostPackMode";
import { TextMode } from "@/features/generate/modes/TextMode";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { cn } from "@/lib/utils";
import { useGenerateStore } from "@/stores/generate";

type Mode = "post" | "text" | "card" | "document";

const MODES: { value: Mode; label: string; icon: typeof Type }[] = [
  { value: "post", label: "LinkedIn post", icon: Megaphone },
  { value: "text", label: "Text post", icon: Type },
  { value: "card", label: "Image card", icon: ImageIcon },
  { value: "document", label: "Document", icon: FileType },
];

const MODE_TITLE: Record<Mode, string> = {
  post: "LinkedIn post — caption + card",
  text: "LinkedIn text post",
  card: "Brand image card",
  document: "Branded document",
};

export function GeneratePage() {
  const { workspace } = useActiveWorkspace();
  // Re-opened from History "Customize" → land directly in the matching mode.
  const hydrate = useGenerateStore((s) => s.hydrate);
  const [mode, setMode] = useState<Mode>(
    hydrate ? (hydrate.type === "post_pack" ? "post" : "card") : "text",
  );

  const corpusReady = (workspace?.ready_chunk_count ?? 0) > 0;
  if (workspace && !corpusReady) {
    return <EmptyCorpus />;
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4 animate-fade-in-up">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
            Generate
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-[-0.01em] text-foreground">
            {MODE_TITLE[mode]}
          </h1>
        </div>
        <div className="flex gap-1 rounded-md border border-border bg-surface p-1">
          {MODES.map((m) => {
            const Icon = m.icon;
            return (
              <button
                key={m.value}
                type="button"
                onClick={() => setMode(m.value)}
                className={cn(
                  "flex items-center gap-1.5 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
                  mode === m.value
                    ? "bg-surface-variant text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {m.label}
              </button>
            );
          })}
        </div>
      </header>

      {mode === "post" && <PostPackMode />}
      {mode === "text" && <TextMode />}
      {mode === "card" && <CardMode />}
      {mode === "document" && <DocumentMode />}
    </div>
  );
}
