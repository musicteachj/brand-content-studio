import { useCallback } from "react";
import { streamPostPackGeneration, type PostPackStreamBody } from "@/lib/sse";
import type {
  CardFields,
  CardTemplate,
  Generation,
  PostPackOutput,
  RetrievalEnvelope,
  SSECardMetaFrame,
} from "@/types";
import { useCardImageSelection } from "./useCardImageSelection";
import { useStreamedGeneration, type Status } from "./useStreamedGeneration";

type Meta = SSECardMetaFrame["meta"];

interface StreamState {
  status: Status;
  caption: string; // the streamed LinkedIn post caption (live typing)
  fields: CardFields | null; // the distilled card fields (from meta, on done)
  suggestedKeywords: string[];
  templateId: CardTemplate;
  accentHex: string | null;
  generationId: string | null;
  retrieval: RetrievalEnvelope | null;
  error: string | null;
}

const initialStream = (templateId: CardTemplate): StreamState => ({
  status: "idle",
  caption: "",
  fields: null,
  suggestedKeywords: [],
  templateId,
  accentHex: null,
  generationId: null,
  retrieval: null,
  error: null,
});

/** Drives the "LinkedIn Post" objective: streams the caption live and captures the
 *  distilled card fields/keywords (shared streaming machine), and manages parallel
 *  image selection (shared with the card hook — ARCH-04, which gives post-pack a
 *  working `clearImage`). The image PATCHes onto the generation's nested card. */
export function usePostPackGeneration(workspaceId: string | null) {
  const { state, setState, generate, stop, abort } = useStreamedGeneration<
    StreamState,
    PostPackStreamBody,
    Meta
  >(workspaceId, {
    initial: initialStream("photo-led"),
    stream: streamPostPackGeneration,
    streamingSeed: (_s, body) => ({
      ...initialStream(body.template_id as CardTemplate),
      status: "streaming",
    }),
    applyText: (s, delta) => ({ ...s, caption: s.caption + delta }),
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

  /** Load a persisted post_pack (re-opened from History) into a "done" state — no
   *  model call. The card lives under `output.card`; image bytes are re-fetched. */
  const loadGeneration = useCallback(
    async (gen: Generation) => {
      if (gen.type !== "post_pack") return;
      abort();
      const out = gen.output as unknown as PostPackOutput;
      const card = out.card;
      setState({
        ...initialStream(card.template_id),
        status: "done",
        caption: out.post_text ?? "",
        fields: card.fields,
        suggestedKeywords: card.suggested_keywords ?? [],
        templateId: card.template_id,
        accentHex: card.accent_hex ?? null,
        generationId: gen.id,
      });
      await hydrate(gen.id, card.image ?? null);
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
