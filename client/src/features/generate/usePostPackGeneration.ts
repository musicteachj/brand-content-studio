import { useCallback, useEffect, useRef, useState } from "react";
import { fetchImageDataUrl, trackUnsplashDownload } from "@/api/images";
import { api } from "@/lib/api";
import { streamPostPackGeneration, type PostPackStreamBody } from "@/lib/sse";
import type {
  CardFields,
  CardImage,
  CardTemplate,
  Generation,
  PostPackOutput,
  RetrievalEnvelope,
  SSECardMetaFrame,
  UnsplashPhoto,
} from "@/types";

type Status = "idle" | "streaming" | "done" | "error";

interface State {
  status: Status;
  caption: string; // the streamed LinkedIn post caption (live typing)
  fields: CardFields | null; // the distilled card fields (from meta, on done)
  suggestedKeywords: string[];
  templateId: CardTemplate;
  accentHex: string | null;
  generationId: string | null;
  retrieval: RetrievalEnvelope | null;
  image: CardImage | null;
  imageDataUrl: string | null;
  imageError: string | null;
  error: string | null;
}

const initial = (templateId: CardTemplate): State => ({
  status: "idle",
  caption: "",
  fields: null,
  suggestedKeywords: [],
  templateId,
  accentHex: null,
  generationId: null,
  retrieval: null,
  image: null,
  imageDataUrl: null,
  imageError: null,
  error: null,
});

/** Drives the "LinkedIn Post" objective: streams the caption live, captures the
 *  distilled card fields/keywords from the terminal meta, and manages parallel
 *  image selection (PATCHed onto the generation's nested card once available). */
export function usePostPackGeneration(workspaceId: string | null) {
  const [state, setState] = useState<State>(initial("photo-led"));
  const abortRef = useRef<AbortController | null>(null);
  const persistedKeyRef = useRef<string | null>(null);

  const generate = useCallback(
    async (body: PostPackStreamBody) => {
      if (!workspaceId) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      persistedKeyRef.current = null; // re-PATCH any kept image onto the new generation
      setState((s) => ({
        ...initial(body.template_id as CardTemplate),
        status: "streaming",
        image: s.image,
        imageDataUrl: s.imageDataUrl,
      }));

      let errored = false;
      await streamPostPackGeneration(
        workspaceId,
        body,
        {
          onText: (delta) => setState((s) => ({ ...s, caption: s.caption + delta })),
          onMeta: (meta: SSECardMetaFrame["meta"]) =>
            setState((s) => ({
              ...s,
              fields: meta.fields,
              suggestedKeywords: meta.suggested_keywords,
              templateId: meta.template_id,
              generationId: meta.generation_id,
              retrieval: meta.retrieval,
            })),
          onError: (message) => {
            errored = true;
            setState((s) => ({ ...s, status: "error", error: message }));
          },
        },
        controller.signal,
      );

      if (!controller.signal.aborted) {
        setState((s) => (errored ? s : { ...s, status: "done" }));
      }
    },
    [workspaceId],
  );

  /** Load a persisted post_pack (re-opened from History) into a "done" state — no
   *  model call. The card lives under `output.card`; image bytes are re-fetched. */
  const loadGeneration = useCallback(async (gen: Generation) => {
    if (gen.type !== "post_pack") return;
    abortRef.current?.abort();
    const out = gen.output as unknown as PostPackOutput;
    const card = out.card;
    const imageKey = card.image?.unsplash_id ?? card.image?.storage_key ?? "none";
    persistedKeyRef.current = `${gen.id}:${imageKey}`;
    setState({
      ...initial(card.template_id),
      status: "done",
      caption: out.post_text ?? "",
      fields: card.fields,
      suggestedKeywords: card.suggested_keywords ?? [],
      templateId: card.template_id,
      accentHex: card.accent_hex ?? null,
      generationId: gen.id,
      image: card.image ?? null,
    });
    if (card.image?.url) {
      try {
        const dataUrl = await fetchImageDataUrl(card.image.url);
        setState((s) => (s.generationId === gen.id ? { ...s, imageDataUrl: dataUrl } : s));
      } catch {
        setState((s) =>
          s.generationId === gen.id ? { ...s, imageError: "Couldn’t load the image." } : s,
        );
      }
    }
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => (s.status === "streaming" ? { ...s, status: "done" } : s));
  }, []);

  const selectUnsplash = useCallback(async (photo: UnsplashPhoto) => {
    void trackUnsplashDownload(photo.download_location);
    try {
      const dataUrl = await fetchImageDataUrl(photo.preview_url);
      setState((s) => ({
        ...s,
        imageError: null,
        imageDataUrl: dataUrl,
        image: {
          source: "unsplash",
          url: photo.preview_url,
          storage_key: null,
          unsplash_id: photo.id,
          attribution: photo.attribution,
        },
      }));
    } catch {
      setState((s) => ({ ...s, imageError: "Couldn’t load that photo. Try another." }));
    }
  }, []);

  const selectUpload = useCallback(async (url: string, storageKey: string) => {
    try {
      const dataUrl = await fetchImageDataUrl(url);
      setState((s) => ({
        ...s,
        imageError: null,
        imageDataUrl: dataUrl,
        image: {
          source: "upload",
          url,
          storage_key: storageKey,
          unsplash_id: null,
          attribution: null,
        },
      }));
    } catch {
      setState((s) => ({ ...s, imageError: "Couldn’t load the uploaded image." }));
    }
  }, []);

  // Persist the selected image onto the generation's card once both exist. The
  // server nests `image` under `output.card` for a post_pack. Idempotent per image.
  useEffect(() => {
    if (!workspaceId || !state.generationId || !state.image) return;
    const key = `${state.generationId}:${state.image.unsplash_id ?? state.image.storage_key ?? "none"}`;
    if (persistedKeyRef.current === key) return;
    persistedKeyRef.current = key;
    api
      .patch(`/workspaces/${workspaceId}/generations/${state.generationId}`, {
        image: state.image,
      })
      .catch(() => {
        persistedKeyRef.current = null; // allow a retry on the next change
      });
  }, [workspaceId, state.generationId, state.image]);

  return { ...state, generate, loadGeneration, stop, selectUnsplash, selectUpload };
}
