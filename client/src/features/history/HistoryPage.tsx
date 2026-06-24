import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { LayoutGrid, Trash2, X } from "lucide-react";
import { useDeleteGeneration, useGenerations, type HistoryFilter } from "@/api/generations";
import { Button } from "@/components/ui/button";
import { RetrievalDebugPanel } from "@/features/generate/RetrievalDebugPanel";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";
import type { Generation, TextOutput } from "@/types";

const FILTERS: { value: HistoryFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "text", label: "Posts" },
  { value: "card", label: "Cards" },
];

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function postText(gen: Generation): string {
  const out = gen.output as TextOutput;
  return typeof out?.post_text === "string" ? out.post_text : "";
}

export function HistoryPage() {
  const { workspaceId } = useActiveWorkspace();
  const [filter, setFilter] = useState<HistoryFilter>("all");
  const { data: generations, isLoading, isError } = useGenerations(workspaceId, filter);
  const [open, setOpen] = useState<Generation | null>(null);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4 animate-fade-in-up">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
            Content History
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-[-0.01em] text-foreground">
            Generations
          </h1>
        </div>
        <div className="flex gap-1 rounded-md border border-border bg-surface p-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={cn(
                "rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
                filter === f.value
                  ? "bg-surface-variant text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </header>

      {isLoading && <SkeletonGrid />}
      {isError && (
        <p className="rounded-lg border border-border bg-surface p-4 text-sm text-destructive">
          Couldn't load history.
        </p>
      )}
      {generations && generations.length === 0 && <EmptyHistory />}
      {generations && generations.length > 0 && (
        <div className="grid animate-fade-in-up gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {generations.map((gen) => (
            <HistoryCard key={gen.id} gen={gen} onOpen={() => setOpen(gen)} />
          ))}
        </div>
      )}

      <DetailDialog gen={open} workspaceId={workspaceId} onClose={() => setOpen(null)} />
    </div>
  );
}

function HistoryCard({ gen, onOpen }: { gen: Generation; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex flex-col rounded-lg border border-border bg-surface p-4 text-left shadow-light transition-transform transition-shadow hover:-translate-y-0.5 hover:shadow-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-center gap-2">
        <span className="rounded-sm bg-surface-variant px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">
          {gen.type}
        </span>
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
          {formatDate(gen.created_at)}
        </span>
      </div>
      <p className="mt-3 line-clamp-2 text-sm font-medium text-foreground">{gen.brief}</p>
      <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
        {postText(gen)}
      </p>
      <span className="mt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
        {gen.retrieved_chunk_ids.length} sources
      </span>
    </button>
  );
}

function DetailDialog({
  gen,
  workspaceId,
  onClose,
}: {
  gen: Generation | null;
  workspaceId: string | null;
  onClose: () => void;
}) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const del = useDeleteGeneration(workspaceId);

  if (!gen) return null;
  // Re-opened from history: the timing/k envelope isn't persisted (only the
  // per-chunk snapshot is), so leave latency/k out rather than showing 0.
  const retrieval = {
    retrieved: gen.retrieval_meta,
    embedding_model: gen.embedding_query_model,
  };

  async function remove() {
    if (!gen) return;
    await del.mutateAsync(gen.id);
    onClose();
  }

  return (
    <Dialog.Root open={!!gen} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-modal bg-foreground/30 backdrop-blur-[1px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-modal flex max-h-[88vh] w-[calc(100vw-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-heavy">
          <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
            <div className="min-w-0">
              <Dialog.Title className="text-sm font-semibold text-foreground">
                {gen.brief}
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                {gen.type} · {gen.model} · {formatDate(gen.created_at)}
              </Dialog.Description>
            </div>
            <Dialog.Close
              aria-label="Close"
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-surface-variant hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X className="h-4 w-4" aria-hidden />
            </Dialog.Close>
          </div>

          <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
            <article className="whitespace-pre-wrap rounded-lg border border-border bg-surface-variant/40 p-4 text-[15px] leading-relaxed text-foreground">
              {postText(gen)}
            </article>
            <RetrievalDebugPanel retrieval={retrieval} />
          </div>

          {!isDemo && (
            <div className="flex justify-end border-t border-border px-6 py-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={remove}
                loading={del.isPending}
                className="text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
                Delete
              </Button>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function EmptyHistory() {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-surface-variant text-muted-foreground">
        <LayoutGrid className="h-5 w-5" aria-hidden />
      </span>
      <p className="mt-4 text-sm font-medium text-foreground">No generations yet</p>
      <p className="mt-1 max-w-xs text-sm text-muted-foreground">
        Generated posts and cards land here, with their retrieval snapshot.
      </p>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className="h-40 animate-pulse rounded-lg border border-border bg-surface-variant/40"
        />
      ))}
    </div>
  );
}
