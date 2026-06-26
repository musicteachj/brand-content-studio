import { useEffect, useState } from "react";
import { Check, Copy, FileText, FileType, Image as ImageIcon, Sparkles, Type } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { CardControlsPanel } from "@/features/generate/CardControlsPanel";
import { CardCustomizePanel } from "@/features/generate/CardCustomizePanel";
import { CardPreview } from "@/features/generate/CardPreview";
import { ControlsPanel } from "@/features/generate/ControlsPanel";
import { DocumentControlsPanel } from "@/features/generate/DocumentControlsPanel";
import { DocumentPreview } from "@/features/generate/DocumentPreview";
import { ImagePickerPanel } from "@/features/generate/ImagePickerPanel";
import { RetrievalDebugPanel } from "@/features/generate/RetrievalDebugPanel";
import { useCardEditor, type CardEditorBase } from "@/features/generate/useCardEditor";
import { useCardGeneration } from "@/features/generate/useCardGeneration";
import { useDocumentGeneration } from "@/features/generate/useDocumentGeneration";
import { useTextGeneration } from "@/features/generate/useTextGeneration";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { cn } from "@/lib/utils";
import { useGenerateStore } from "@/stores/generate";
import type { CardTemplate, DocumentArchetype, Length, Tone } from "@/types";

type Mode = "text" | "card" | "document";

const MODES: { value: Mode; label: string; icon: typeof Type }[] = [
  { value: "text", label: "Text post", icon: Type },
  { value: "card", label: "Image card", icon: ImageIcon },
  { value: "document", label: "Document", icon: FileType },
];

const MODE_TITLE: Record<Mode, string> = {
  text: "LinkedIn text post",
  card: "Brand image card",
  document: "Branded document",
};

export function GeneratePage() {
  const { workspace } = useActiveWorkspace();
  // Re-opened from History "Customize" → land directly in card mode.
  const hydratePending = useGenerateStore((s) => s.hydrate !== null);
  const [mode, setMode] = useState<Mode>(hydratePending ? "card" : "text");

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

      {mode === "text" && <TextMode />}
      {mode === "card" && <CardMode />}
      {mode === "document" && <DocumentMode />}
    </div>
  );
}

function DocumentMode() {
  const { workspace, workspaceId } = useActiveWorkspace();
  const [brief, setBrief] = useState("");
  const [tone, setTone] = useState<Tone>("default");
  const [archetype, setArchetype] = useState<DocumentArchetype>("one-pager");
  const gen = useDocumentGeneration(workspaceId);
  const isStreaming = gen.status === "streaming";
  const brand = workspace?.brand_profile ?? null;

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <div className="lg:sticky lg:top-6 lg:self-start">
        <DocumentControlsPanel
          brief={brief}
          setBrief={setBrief}
          archetype={archetype}
          setArchetype={setArchetype}
          tone={tone}
          setTone={setTone}
          isStreaming={isStreaming}
          onGenerate={() => gen.generate({ brief, archetype, tone })}
          onStop={gen.stop}
        />
      </div>
      <div className="flex flex-col gap-6">
        {brand && (
          <DocumentPreview
            status={gen.status}
            text={gen.text}
            document={gen.document}
            archetype={gen.archetype}
            formats={gen.formats}
            generationId={gen.generationId}
            workspaceId={workspaceId}
            brand={brand}
            error={gen.error}
          />
        )}
        <RetrievalDebugPanel retrieval={gen.retrieval} />
      </div>
    </div>
  );
}

function TextMode() {
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

function CardMode() {
  const { workspace, workspaceId } = useActiveWorkspace();
  const [brief, setBrief] = useState("");
  const [tone, setTone] = useState<Tone>("default");
  const [template, setTemplate] = useState<CardTemplate | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const gen = useCardGeneration(workspaceId);
  const isStreaming = gen.status === "streaming";

  // Consume a History → Customize hand-off once: load the persisted card into the
  // editor (no /generate). The store is cleared so a remount doesn't reload it.
  const hydrate = useGenerateStore((s) => s.hydrate);
  const setHydrate = useGenerateStore((s) => s.setHydrate);
  useEffect(() => {
    if (hydrate && hydrate.type === "card") {
      void gen.loadGeneration(hydrate);
      setHydrate(null);
    }
    // Run once on mount; the hand-off is a one-shot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Once the card is generated, hand its persisted state to the editor: layout
  // swap, accent, and inline copy edits are all client-side (PATCH on Save, never
  // a /generate). Until then there's nothing to customize.
  const editorBase: CardEditorBase | null =
    gen.status === "done" && gen.fields && gen.generationId
      ? {
          generationId: gen.generationId,
          template: gen.templateId,
          fields: gen.fields,
          accentHex: gen.accentHex,
        }
      : null;
  const editor = useCardEditor(workspaceId, editorBase);
  const editing = editorBase !== null;
  const [editingText, setEditingText] = useState(false);

  // Leave inline-edit mode whenever there's nothing to edit (e.g. after a
  // regenerate starts a fresh stream).
  useEffect(() => {
    if (!editing) setEditingText(false);
  }, [editing]);

  const brand = workspace?.brand_profile;
  if (!brand) return null;

  // The preview renders from the editor draft when editing (so unsaved swaps/edits
  // show live), otherwise from the live generation stream.
  const previewTemplate = editing ? editor.template : gen.templateId;
  const previewFields = editing ? editor.fields : gen.fields;
  const previewAccent = editing ? editor.accentHex : gen.accentHex;

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <div className="lg:sticky lg:top-6 lg:self-start">
        <CardControlsPanel
          brand={brand}
          brief={brief}
          setBrief={setBrief}
          tone={tone}
          setTone={setTone}
          template={template}
          setTemplate={setTemplate}
          isStreaming={isStreaming}
          hasGenerated={gen.status !== "idle"}
          onGenerate={() => template && gen.generate({ brief, template_id: template, tone })}
          onStop={gen.stop}
        />
      </div>

      <div className="flex flex-col gap-6">
        <CardPreview
          status={gen.status}
          copy={gen.copy}
          template={previewTemplate}
          fields={previewFields}
          brand={brand}
          accentHex={previewAccent}
          imageDataUrl={gen.imageDataUrl}
          attribution={gen.image?.attribution ?? null}
          error={gen.error}
          hasImage={gen.image !== null}
          imageError={gen.imageError}
          onAddImage={() => setPickerOpen(true)}
          editingText={editing && editingText}
          onToggleEditText={editing ? () => setEditingText((v) => !v) : undefined}
          onEditField={editing ? editor.setField : undefined}
          editKey={`${gen.generationId ?? ""}:${editor.template}`}
        />
        {editing && (
          <CardCustomizePanel
            brand={brand}
            template={editor.template}
            accentHex={editor.accentHex}
            dirty={editor.dirty}
            saving={editor.saving}
            saveError={editor.saveError}
            onTemplate={editor.setTemplate}
            onAccent={editor.setAccent}
            onSave={() => void editor.save()}
            onDiscard={editor.discard}
          />
        )}
        <RetrievalDebugPanel retrieval={gen.retrieval} />
      </div>

      <ImagePickerPanel
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        workspaceId={workspaceId}
        initialKeywords={gen.suggestedKeywords}
        selectedKey={gen.image?.unsplash_id ?? gen.image?.storage_key ?? null}
        onSelectUnsplash={(p) => {
          void gen.selectUnsplash(p);
        }}
        onSelectUpload={(url, key) => {
          void gen.selectUpload(url, key);
        }}
      />
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
              aria-live="polite"
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

function EmptyCorpus() {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-[60vh] animate-fade-in-up flex-col items-center justify-center text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-surface text-muted-foreground shadow-light">
        <FileText className="h-6 w-6" aria-hidden />
      </span>
      <h1 className="mt-5 text-xl font-semibold text-foreground">Ingest assets first</h1>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        This workspace has no retrievable brand corpus yet. Upload brand documents so generation has
        something on-brand to work from.
      </p>
      <Button className="mt-5" onClick={() => navigate("/assets")}>
        Open Asset Manager
      </Button>
    </div>
  );
}
