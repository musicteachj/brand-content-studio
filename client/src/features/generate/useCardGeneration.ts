import { useCallback } from "react";
import { streamCardGeneration, type CardStreamBody } from "@/lib/sse";
import type {
  CardFields,
  CardOutput,
  CardTemplate,
  Generation,
  RetrievalEnvelope,
  SSECardMetaFrame,
} from "@/types";
import { useCardImageSelection } from "./useCardImageSelection";
import { useStreamedGeneration, type Status } from "./useStreamedGeneration";

type Meta = SSECardMetaFrame["meta"];

interface StreamState {
  status: Status;
  copy: string; // streamed prose for the live "drafting" typing effect
  fields: CardFields | null; // structured fields (from tool-use, on done)
  suggestedKeywords: string[];
  templateId: CardTemplate;
  accentHex: string | null; // per-card accent (null for a fresh card; set on history hydrate)
  generationId: string | null;
  retrieval: RetrievalEnvelope | null;
  error: string | null;
}

const initialStream = (templateId: CardTemplate): StreamState => ({
  status: "idle",
  copy: "",
  fields: null,
  suggestedKeywords: [],
  templateId,
  accentHex: null,
  generationId: null,
  retrieval: null,
  error: null,
});

/** Drives a single streamed card generation: streams the draft copy, captures the
 *  terminal fields/keywords (shared streaming machine), and manages image selection
 *  (shared with the post-pack hook — ARCH-04). Because image selection lives in its
 *  own hook, a picked image survives a regenerate and re-attaches to the new id. */
export function useCardGeneration(workspaceId: string | null) {
  const { state, setState, generate, stop, abort } = useStreamedGeneration<
    StreamState,
    CardStreamBody,
    Meta
  >(workspaceId, {
    initial: initialStream("photo-led"),
    stream: streamCardGeneration,
    streamingSeed: (_s, body) => ({
      ...initialStream(body.template_id as CardTemplate),
      status: "streaming",
    }),
    applyText: (s, delta) => ({ ...s, copy: s.copy + delta }),
    applyMeta: (s, meta) => ({
      ...s,
      fields: meta.fields,
      suggestedKeywords: meta.suggested_keywords,
      templateId: meta.template_id,
      generationId: meta.generation_id,
      retrieval: meta.retrieval,
    }),
  });

  const {
    image,
    imageDataUrl,
    imageError,
    selectUnsplash,
    selectUpload,
    clearImage,
    hydrate,
    reset: resetImage,
  } = useCardImageSelection(workspaceId, state.generationId);

  /** Load a persisted card generation (re-opened from History) into a "done" state
   *  so it can be customized — layout/accent/copy edits and image swaps — with NO
   *  model call. Image bytes are fetched fresh for render/export. */
  const loadGeneration = useCallback(
    async (gen: Generation) => {
      if (gen.type !== "card") return;
      abort();
      const out = gen.output as unknown as CardOutput;
      setState({
        ...initialStream(out.template_id),
        status: "done",
        fields: out.fields,
        suggestedKeywords: out.suggested_keywords ?? [],
        templateId: out.template_id,
        accentHex: out.accent_hex ?? null,
        generationId: gen.id,
      });
      await hydrate(gen.id, out.image ?? null);
    },
    [abort, setState, hydrate],
  );

  const reset = useCallback(() => {
    abort();
    setState(initialStream("photo-led"));
    resetImage();
  }, [abort, setState, resetImage]);

  return {
    ...state,
    image,
    imageDataUrl,
    imageError,
    generate,
    loadGeneration,
    stop,
    reset,
    selectUnsplash,
    selectUpload,
    clearImage,
  };
}
