import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { Check, Copy, Download, LayoutGrid, Sliders, Trash2, X } from "lucide-react";
import { useDeleteGeneration, useGenerations, type HistoryFilter } from "@/api/generations";
import { flattenPages } from "@/api/pagination";
import { Button } from "@/components/ui/button";
import { CardThumb } from "@/features/generate/cards/CardThumb";
import { DocumentArtifact } from "@/features/generate/DocumentArtifact";
import { DocumentDownloadRow } from "@/features/generate/DocumentDownloadRow";
import { downloadCardPng } from "@/features/generate/useCardExport";
import { RetrievalDebugPanel } from "@/features/generate/RetrievalDebugPanel";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { injectBrandFontFaces } from "@/styles/brandFonts";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";
import { useGenerateStore } from "@/stores/generate";
import type {
  BrandProfile,
  CardOutput,
  DocumentOutput,
  Generation,
  PostPackOutput,
  TextOutput,
} from "@/types";

const FILTERS: { value: HistoryFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "post_pack", label: "LinkedIn" },
  { value: "text", label: "Posts" },
  { value: "card", label: "Cards" },
  { value: "document", label: "Documents" },
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

function cardOutput(gen: Generation): CardOutput | null {
  const out = gen.output as unknown as CardOutput;
  return gen.type === "card" && out?.template_id ? out : null;
}

/** The renderable card for a generation: a `card` carries it at the top of
 *  `output`; a `post_pack` nests it under `output.card`. */
function cardFrom(gen: Generation): CardOutput | null {
  if (gen.type === "card") return cardOutput(gen);
  if (gen.type === "post_pack") {
    const out = gen.output as unknown as PostPackOutput;
    return out?.card?.template_id ? out.card : null;
  }
  return null;
}

function documentOutput(gen: Generation): DocumentOutput | null {
  const out = gen.output as unknown as DocumentOutput;
  return gen.type === "document" && out?.document ? out : null;
}

/** Copy-text (posts) + download-PNG (cards) actions, shared by the grid card and
 *  the detail dialog. The PNG download re-exports from the persisted output with
 *  no model call. Transient state resets when the generation changes. */
function useGenerationActions(gen: Generation | null, brand: BrandProfile | null) {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  // Memoized so `download`'s dependency is stable across renders. Covers cards
  // and the nested card of a post_pack.
  const card = useMemo(() => (gen ? cardFrom(gen) : null), [gen]);

  // Reset all transient action state when a different generation is opened
  // (the dialog reuses one hook instance across generations).
  useEffect(() => {
    setCopied(false);
    setDownloading(false);
    setDownloadError(null);
  }, [gen?.id]);

  const copyText = useCallback(async () => {
    if (!gen) return;
    await navigator.clipboard.writeText(postText(gen));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [gen]);

  const download = useCallback(async () => {
    if (!card || !brand) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadCardPng(card, brand);
    } catch (err) {
      setDownloadError((err as Error).message);
    } finally {
      setDownloading(false);
    }
  }, [card, brand]);

  return { card, copied, copyText, downloading, downloadError, download };
}

export function HistoryPage() {
  const { workspace, workspaceId } = useActiveWorkspace();
  const brand = workspace?.brand_profile ?? null;
  const [filter, setFilter] = useState<HistoryFilter>("all");
  const { data, isLoading, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useGenerations(workspaceId, filter);
  const generations = flattenPages(data);
  const [open, setOpen] = useState<Generation | null>(null);

  // Load workspace fonts so card thumbnails render in the brand type.
  useEffect(() => {
    if (brand) injectBrandFontFaces(brand.fonts);
  }, [brand]);

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
      {!isLoading && !isError && generations.length === 0 && <EmptyHistory />}
      {generations.length > 0 && (
        <div className="grid animate-fade-in-up gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {generations.map((gen) => (
            <HistoryCard
              key={gen.id}
              gen={gen}
              brand={brand}
              workspaceId={workspaceId}
              onOpen={() => setOpen(gen)}
            />
          ))}
        </div>
      )}
      {hasNextPage && (
        <div className="flex justify-center">
          <Button variant="secondary" onClick={() => fetchNextPage()} loading={isFetchingNextPage}>
            Load more
          </Button>
        </div>
      )}

      <DetailDialog
        gen={open}
        brand={brand}
        workspaceId={workspaceId}
        onClose={() => setOpen(null)}
      />
    </div>
  );
}

function HistoryCard({
  gen,
  brand,
  workspaceId,
  onOpen,
}: {
  gen: Generation;
  brand: BrandProfile | null;
  workspaceId: string | null;
  onOpen: () => void;
}) {
  // Outer is a div (not a button) so the inline action buttons aren't nested
  // inside an interactive element. The content area is its own trigger button.
  const { card, copied, copyText, downloading, downloadError, download } = useGenerationActions(
    gen,
    brand,
  );
  const doc = documentOutput(gen);
  const isPost = gen.type === "post_pack";
  return (
    <div className="flex flex-col rounded-lg border border-border bg-surface shadow-light transition-transform transition-shadow hover:-translate-y-0.5 hover:shadow-medium">
      <button
        type="button"
        onClick={onOpen}
        className="flex flex-1 flex-col rounded-t-lg p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      >
        <div className="flex items-center gap-2">
          <span className="rounded-sm bg-surface-variant px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">
            {isPost ? "post + card" : gen.type}
          </span>
          <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
            {formatDate(gen.created_at)}
          </span>
        </div>
        <p className="mt-3 line-clamp-2 text-sm font-medium text-foreground">{gen.brief}</p>
        {card && brand ? (
          <>
            <div className="mt-3 overflow-hidden rounded-md border border-border">
              <CardThumb output={card} brand={brand} />
            </div>
            {isPost && (
              <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                {postText(gen)}
              </p>
            )}
          </>
        ) : doc && brand ? (
          <div className="mt-3 max-h-44 overflow-hidden rounded-md border border-border">
            <DocumentArtifact document={doc.document} brand={brand} compact />
          </div>
        ) : (
          <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
            {postText(gen)}
          </p>
        )}
        <span className="mt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          {gen.retrieved_chunk_ids.length} sources
        </span>
      </button>
      <div className="flex items-center gap-1 border-t border-border px-2 py-1.5">
        {card ? (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={download}
              loading={downloading}
              disabled={!brand}
            >
              <Download className="h-4 w-4" aria-hidden />
              Download
            </Button>
            {isPost && (
              <Button variant="ghost" size="sm" onClick={copyText}>
                {copied ? (
                  <Check className="h-4 w-4 text-success" aria-hidden />
                ) : (
                  <Copy className="h-4 w-4" aria-hidden />
                )}
                {copied ? "Copied" : "Caption"}
              </Button>
            )}
          </>
        ) : doc ? (
          <DocumentDownloadRow
            workspaceId={workspaceId}
            generationId={gen.id}
            output={doc}
            className="px-1"
          />
        ) : (
          <Button variant="ghost" size="sm" onClick={copyText}>
            {copied ? (
              <Check className="h-4 w-4 text-success" aria-hidden />
            ) : (
              <Copy className="h-4 w-4" aria-hidden />
            )}
            {copied ? "Copied" : "Copy"}
          </Button>
        )}
        {downloadError && (
          <span role="alert" className="truncate text-xs text-destructive">
            {downloadError}
          </span>
        )}
      </div>
    </div>
  );
}

function DetailDialog({
  gen,
  brand,
  workspaceId,
  onClose,
}: {
  gen: Generation | null;
  brand: BrandProfile | null;
  workspaceId: string | null;
  onClose: () => void;
}) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const navigate = useNavigate();
  const setHydrate = useGenerateStore((s) => s.setHydrate);
  const del = useDeleteGeneration(workspaceId);
  const { card, copied, copyText, downloading, downloadError, download } = useGenerationActions(
    gen,
    brand,
  );

  function customize() {
    if (!gen) return;
    // Hand this card to the Generate editor (layout/accent/copy edits, image
    // swap) — no model call. Cleared once consumed there.
    setHydrate(gen);
    onClose();
    navigate("/generate");
  }

  if (!gen) return null;
  const doc = documentOutput(gen);
  const isPost = gen.type === "post_pack";
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
            {card && brand ? (
              <>
                <div className="mx-auto w-full max-w-[320px] overflow-hidden rounded-lg border border-border shadow-light">
                  <CardThumb output={card} brand={brand} />
                </div>
                {isPost && (
                  <article className="whitespace-pre-wrap rounded-lg border border-border bg-surface-variant/40 p-4 text-[15px] leading-relaxed text-foreground">
                    {postText(gen)}
                  </article>
                )}
              </>
            ) : doc && brand ? (
              <div className="overflow-hidden rounded-lg border border-border bg-surface p-3 shadow-light">
                <DocumentArtifact document={doc.document} brand={brand} />
              </div>
            ) : (
              <article className="whitespace-pre-wrap rounded-lg border border-border bg-surface-variant/40 p-4 text-[15px] leading-relaxed text-foreground">
                {postText(gen)}
              </article>
            )}
            <RetrievalDebugPanel retrieval={retrieval} />
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-border px-6 py-3">
            <div className="flex items-center gap-2">
              {card ? (
                <>
                  <Button variant="secondary" size="sm" onClick={customize} disabled={!brand}>
                    <Sliders className="h-4 w-4" aria-hidden />
                    Customize
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={download}
                    loading={downloading}
                    disabled={!brand}
                  >
                    <Download className="h-4 w-4" aria-hidden />
                    Download PNG
                  </Button>
                  {isPost && (
                    <Button variant="ghost" size="sm" onClick={copyText}>
                      {copied ? (
                        <Check className="h-4 w-4 text-success" aria-hidden />
                      ) : (
                        <Copy className="h-4 w-4" aria-hidden />
                      )}
                      {copied ? "Copied" : "Copy caption"}
                    </Button>
                  )}
                </>
              ) : doc ? (
                <DocumentDownloadRow workspaceId={workspaceId} generationId={gen.id} output={doc} />
              ) : (
                <Button variant="secondary" size="sm" onClick={copyText}>
                  {copied ? (
                    <Check className="h-4 w-4 text-success" aria-hidden />
                  ) : (
                    <Copy className="h-4 w-4" aria-hidden />
                  )}
                  {copied ? "Copied" : "Copy text"}
                </Button>
              )}
              {downloadError && (
                <span role="alert" className="text-xs text-destructive">
                  {downloadError}
                </span>
              )}
            </div>
            {!isDemo && (
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
            )}
          </div>
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
        Generated posts, cards, and documents land here, with their retrieval snapshot.
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
