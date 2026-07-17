import { useEffect, useRef, useState } from "react";
import { useAddBrandImage } from "@/api/workspaces";
import { CardControlsPanel } from "@/features/generate/CardControlsPanel";
import { CardCustomizePanel } from "@/features/generate/CardCustomizePanel";
import { CardPreview } from "@/features/generate/CardPreview";
import { ImagePickerPanel } from "@/features/generate/ImagePickerPanel";
import { RetrievalDebugPanel } from "@/features/generate/RetrievalDebugPanel";
import { useCardEditor, type CardEditorBase } from "@/features/generate/useCardEditor";
import { useCardGeneration } from "@/features/generate/useCardGeneration";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { useAuthStore } from "@/stores/auth";
import { useGenerateStore } from "@/stores/generate";
import type { CardPreset, CardTemplate, Tone } from "@/types";

export function CardMode() {
  const { workspace, workspaceId } = useActiveWorkspace();
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const addBrandImage = useAddBrandImage(workspaceId);
  const [brief, setBrief] = useState("");
  const [tone, setTone] = useState<Tone>("default");
  const [template, setTemplate] = useState<CardTemplate | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  // A selected preset sets the template now and stashes its accent to apply once
  // the card exists (accent is a post-gen PATCH, not part of /generate).
  const [pendingAccent, setPendingAccent] = useState<string | null>(null);
  const presetAppliedRef = useRef<string | null>(null);
  const gen = useCardGeneration(workspaceId);
  const isStreaming = gen.status === "streaming";

  function applyPreset(p: CardPreset) {
    setTemplate(p.template_id);
    setPendingAccent(p.accent_hex);
  }

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

  // Once a card generated from a preset lands, seed its accent (a dirty edit the
  // user can Save). Keyed by generationId (not consumed), so a later Regenerate
  // re-applies the preset's accent to the fresh card — but only once per card, so
  // the user's own accent edits within a card aren't clobbered.
  useEffect(() => {
    if (
      pendingAccent &&
      editing &&
      gen.generationId &&
      presetAppliedRef.current !== gen.generationId
    ) {
      presetAppliedRef.current = gen.generationId;
      editor.setAccent(pendingAccent);
    }
  }, [pendingAccent, editing, gen.generationId, editor]);

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
          presets={brand.card_presets ?? []}
          onApplyPreset={applyPreset}
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
          onClearImage={gen.clearImage}
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
        brandImages={workspace?.brand_profile.brand_images ?? []}
        onSaveBrandImage={
          isDemo ? undefined : (file) => addBrandImage.mutateAsync(file).then(() => undefined)
        }
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
