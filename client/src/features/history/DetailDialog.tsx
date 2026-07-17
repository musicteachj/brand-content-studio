import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { Check, Copy, Download, Sliders, Trash2, X } from "lucide-react";
import { useDeleteGeneration } from "@/api/generations";
import { Button } from "@/components/ui/button";
import { CardThumb } from "@/features/generate/cards/CardThumb";
import { DocumentArtifact } from "@/features/generate/DocumentArtifact";
import { DocumentDownloadRow } from "@/features/generate/DocumentDownloadRow";
import { RetrievalDebugPanel } from "@/features/generate/RetrievalDebugPanel";
import { useAuthStore } from "@/stores/auth";
import { useGenerateStore } from "@/stores/generate";
import type { BrandProfile, Generation } from "@/types";
import { documentOutput, formatDate, postText } from "./historyOutputs";
import { useGenerationActions } from "./useGenerationActions";

export function DetailDialog({
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
