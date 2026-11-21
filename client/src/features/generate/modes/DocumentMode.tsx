import { useState } from "react";
import { DocumentControlsPanel } from "@/features/generate/DocumentControlsPanel";
import { DocumentPreview } from "@/features/generate/DocumentPreview";
import { RetrievalDebugPanel } from "@/features/generate/RetrievalDebugPanel";
import { useDocumentGeneration } from "@/features/generate/useDocumentGeneration";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import type { DocumentArchetype, Tone } from "@/types";

export function DocumentMode() {
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
