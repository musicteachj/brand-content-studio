import { useCallback, useEffect, useRef, useState } from "react";
import { fetchImageDataUrl, trackUnsplashDownload } from "@/api/images";
import { api } from "@/lib/api";
import { streamCardGeneration, type CardStreamBody } from "@/lib/sse";
import type {
  CardFields,
  CardImage,
  CardTemplate,
  RetrievalEnvelope,
  SSECardMetaFrame,
  UnsplashPhoto,
} from "@/types";

type Status = "idle" | "streaming" | "done" | "error";

interface State {
  status: Status;
  copy: string; // streamed prose for the live "drafting" typing effect
  fields: CardFields | null; // structured fields (from tool-use, on done)
  suggestedKeywords: string[];
  templateId: CardTemplate;
  generationId: string | null;
  retrieval: RetrievalEnvelope | null;
  image: CardImage | null; // persisted shape
  imageDataUrl: string | null; // client-only, for rendering + export
  imageError: string | null; // surfaced when an image fetch fails
  error: string | null;
}

const initial = (templateId: CardTemplate): State => ({
  status: "idle",
  copy: "",
  fields: null,
  suggestedKeywords: [],
  templateId,
  generationId: null,
  retrieval: null,
  image: null,
  imageDataUrl: null,
  imageError: null,
  error: null,
});

/** Drives a single streamed card generation: streams the draft copy, captures the
 *  terminal fields/keywords, and manages image selection (which runs in parallel
 *  and is persisted to the generation via PATCH once both are available). */
export function useCardGeneration(workspaceId: string | null) {
  const [state, setState] = useState<State>(initial("photo-led"));
  const abortRef = useRef<AbortController | null>(null);
  const persistedKeyRef = useRef<string | null>(null);

  const generate = useCallback(
    async (body: CardStreamBody) => {
      if (!workspaceId) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      persistedKeyRef.current = null; // re-PATCH any kept image onto the new generation
      // Image selection is parallel to copy: a photo picked before (or kept from a
      // prior) generation survives a (re)generate and is re-attached to the new id.
      setState((s) => ({
        ...initial(body.template_id as CardTemplate),
        status: "streaming",
        image: s.image,
        imageDataUrl: s.imageDataUrl,
      }));

      let errored = false;
      await streamCardGeneration(
        workspaceId,
        body,
        {
          onText: (delta) => setState((s) => ({ ...s, copy: s.copy + delta })),
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

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => (s.status === "streaming" ? { ...s, status: "done" } : s));
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(initial("photo-led"));
  }, []);

  /** Select an Unsplash photo: fire download tracking (license), fetch the bytes
   *  as a data URL for rendering/export, and store the persisted image shape. A
   *  fetch failure is surfaced rather than swallowed. */
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

  /** Use an uploaded image (already stored server-side; `url` is auth-gated). */
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

  const clearImage = useCallback(() => {
    setState((s) => ({ ...s, image: null, imageDataUrl: null, imageError: null }));
  }, []);

  // Persist the selected image onto the generation once both exist (idempotent
  // per image via a key, so we don't re-PATCH on every render).
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

  return { ...state, generate, stop, reset, selectUnsplash, selectUpload, clearImage };
}
