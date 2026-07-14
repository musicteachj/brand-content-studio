// The document preview is the hero on Document mode: the draft streams in as
// prose (the live "drafting" state), then resolves into the branded one-pager
// "paper" with a multi-format download row. Mirrors the card flow (drafting →
// locked preview) and the North Star (the artifact is the focus, DESIGN §0).
import { FileText } from "lucide-react";
import { DeckPreview } from "@/features/generate/DeckPreview";
import { DocumentDownloadRow } from "@/features/generate/DocumentDownloadRow";
import { DocumentPage } from "@/features/generate/DocumentPage";
import { StreamAnnouncer } from "@/features/generate/StreamAnnouncer";
import type {
  BrandProfile,
  DocumentArchetype,
  DocumentFormat,
  DocumentFormatRef,
  DocumentModel,
} from "@/types";

interface Props {
  status: "idle" | "streaming" | "done" | "error";
  text: string;
  document: DocumentModel | null;
  archetype: DocumentArchetype;
  formats: Partial<Record<DocumentFormat, DocumentFormatRef>>;
  generationId: string | null;
  workspaceId: string | null;
  brand: BrandProfile;
  error: string | null;
}

export function DocumentPreview({
  status,
  text,
  document: doc,
  formats,
  generationId,
  workspaceId,
  brand,
  error,
}: Props) {
  const showPaper = status === "done" && doc !== null;

  return (
    <div className="rounded-xl bg-preview-bg p-5 sm:p-8">
      <StreamAnnouncer status={status} label="Document" />
      {status === "idle" && (
        <div className="mx-auto flex min-h-[280px] w-full max-w-2xl flex-col items-center justify-center rounded-xl border border-border bg-surface p-8 text-center shadow-preview">
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-surface-variant text-muted-foreground">
            <FileText className="h-5 w-5" aria-hidden />
          </span>
          <p className="mt-4 text-sm font-medium text-foreground">Your document will appear here</p>
          <p className="mt-1 max-w-xs text-sm text-muted-foreground">
            Enter a brief and generate — it drafts live, then downloads as branded, on-brand files.
          </p>
        </div>
      )}

      {status === "error" && (
        <div className="mx-auto w-full max-w-2xl rounded-xl border border-border bg-surface p-6 shadow-preview">
          <p role="alert" className="text-sm text-destructive">
            {error ?? "Generation failed."}
          </p>
        </div>
      )}

      {status === "streaming" && (
        <div className="mx-auto w-full max-w-2xl rounded-xl border border-border bg-surface p-7 shadow-preview sm:p-9">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Drafting
          </p>
          <div
            aria-busy="true"
            className="mt-3 whitespace-pre-wrap text-[15px] leading-relaxed text-foreground"
          >
            {text}
            <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-accent align-middle" />
          </div>
        </div>
      )}

      {showPaper && (
        <div className="flex flex-col gap-4">
          {doc.archetype === "short-deck" ? (
            <DeckPreview document={doc} brand={brand} className="mx-auto w-full max-w-2xl" />
          ) : (
            <div className="mx-auto w-full max-w-2xl overflow-hidden rounded-xl shadow-preview ring-1 ring-border">
              <DocumentPage document={doc} brand={brand} />
            </div>
          )}
          {generationId && (
            <div className="mx-auto flex w-full max-w-2xl flex-wrap items-center justify-between gap-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                Branded · ready to download
              </span>
              <DocumentDownloadRow
                workspaceId={workspaceId}
                generationId={generationId}
                output={{ document: doc, formats }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
