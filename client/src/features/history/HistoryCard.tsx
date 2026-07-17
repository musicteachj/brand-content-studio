import { Check, Copy, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CardThumb } from "@/features/generate/cards/CardThumb";
import { DocumentArtifact } from "@/features/generate/DocumentArtifact";
import { DocumentDownloadRow } from "@/features/generate/DocumentDownloadRow";
import type { BrandProfile, Generation } from "@/types";
import { documentOutput, formatDate, postText } from "./historyOutputs";
import { useGenerationActions } from "./useGenerationActions";

export function HistoryCard({
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
