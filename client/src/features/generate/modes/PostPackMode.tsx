import { useEffect, useState } from "react";
import { useAddBrandImage } from "@/api/workspaces";
import { CardPreview } from "@/features/generate/CardPreview";
import { ImagePickerPanel } from "@/features/generate/ImagePickerPanel";
import { PostCaptionPanel } from "@/features/generate/PostCaptionPanel";
import { PostControlsPanel } from "@/features/generate/PostControlsPanel";
import { RetrievalDebugPanel } from "@/features/generate/RetrievalDebugPanel";
import { usePostPackGeneration } from "@/features/generate/usePostPackGeneration";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { useAuthStore } from "@/stores/auth";
import { useGenerateStore } from "@/stores/generate";
import type { CardTemplate, Tone } from "@/types";

export function PostPackMode() {
  const { workspace, workspaceId } = useActiveWorkspace();
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const addBrandImage = useAddBrandImage(workspaceId);
  const [brief, setBrief] = useState("");
  const [tone, setTone] = useState<Tone>("default");
  const [template, setTemplate] = useState<CardTemplate>("photo-led");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [captionDraft, setCaptionDraft] = useState("");
  const gen = usePostPackGeneration(workspaceId);
  const isStreaming = gen.status === "streaming";

  // Consume a History → Customize hand-off once (no /generate).
  const hydrate = useGenerateStore((s) => s.hydrate);
  const setHydrate = useGenerateStore((s) => s.setHydrate);
  useEffect(() => {
    if (hydrate && hydrate.type === "post_pack") {
      void gen.loadGeneration(hydrate);
      setHydrate(null);
    }
    // Run once on mount; the hand-off is a one-shot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Seed the editable caption from the generated caption once the stream finishes.
  useEffect(() => {
    if (gen.status === "done") setCaptionDraft(gen.caption);
  }, [gen.status, gen.caption]);

  const brand = workspace?.brand_profile;
  if (!brand) return null;

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <div className="lg:sticky lg:top-6 lg:self-start">
        <PostControlsPanel
          brand={brand}
          brief={brief}
          setBrief={setBrief}
          tone={tone}
          setTone={setTone}
          template={template}
          setTemplate={setTemplate}
          isStreaming={isStreaming}
          hasGenerated={gen.status !== "idle"}
          onGenerate={() => gen.generate({ brief, tone, template_id: template })}
          onStop={gen.stop}
        />
      </div>

      <div className="flex flex-col gap-6">
        <div className="grid gap-6 xl:grid-cols-2">
          <CardPreview
            status={gen.status}
            copy=""
            template={gen.templateId}
            fields={gen.fields}
            brand={brand}
            accentHex={gen.accentHex}
            imageDataUrl={gen.imageDataUrl}
            attribution={gen.image?.attribution ?? null}
            error={gen.error}
            hasImage={gen.image !== null}
            imageError={gen.imageError}
            onAddImage={() => setPickerOpen(true)}
            onClearImage={gen.clearImage}
            removingImage={gen.removingImage}
          />
          <PostCaptionPanel
            status={gen.status}
            streamingText={gen.caption}
            value={captionDraft}
            onChange={setCaptionDraft}
            error={gen.error}
          />
        </div>
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
