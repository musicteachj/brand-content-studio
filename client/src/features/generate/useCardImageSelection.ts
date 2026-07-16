import { useCallback, useEffect, useRef, useState } from "react";
import { fetchImageDataUrl, trackUnsplashDownload } from "@/api/images";
import { api } from "@/lib/api";
import type { CardImage, UnsplashPhoto } from "@/types";

interface ImageState {
  image: CardImage | null; // persisted shape
  imageDataUrl: string | null; // client-only, for rendering + export
  imageError: string | null; // surfaced when an image fetch fails
}

const EMPTY: ImageState = { image: null, imageDataUrl: null, imageError: null };

const imageKey = (image: CardImage) => image.unsplash_id ?? image.storage_key ?? "none";

/** The card-image concern shared by the card + post-pack generation hooks (ARCH-04):
 *  pick an Unsplash photo or an uploaded image, clear it, hydrate an already-
 *  persisted image from History, and PATCH the selection onto the generation once
 *  both an image and a generation id exist. Image selection is parallel to the copy
 *  stream, so this lives outside the streaming state — a picked image therefore
 *  survives a regenerate and re-attaches to the new generation id. */
export function useCardImageSelection(workspaceId: string | null, generationId: string | null) {
  const [state, setState] = useState<ImageState>(EMPTY);
  // Idempotency guard for the persist PATCH, keyed `${generationId}:${imageKey}`.
  const persistedKeyRef = useRef<string | null>(null);
  // Bumped on every hydrate/reset/workspace-switch so a slow fetchImageDataUrl
  // from a prior generation can't write its bytes into the current one.
  const epochRef = useRef(0);

  // Switching workspaces clears any picked image (the streaming hook aborts).
  useEffect(() => {
    epochRef.current += 1;
    persistedKeyRef.current = null;
    setState(EMPTY);
  }, [workspaceId]);

  /** Select an Unsplash photo: fire download tracking (license), fetch the bytes as
   *  a data URL for rendering/export, and store the persisted image shape. A fetch
   *  failure is surfaced rather than swallowed. */
  const selectUnsplash = useCallback(async (photo: UnsplashPhoto) => {
    void trackUnsplashDownload(photo.download_location);
    const epoch = ++epochRef.current;
    try {
      const dataUrl = await fetchImageDataUrl(photo.preview_url);
      if (epochRef.current !== epoch) return;
      setState({
        imageError: null,
        imageDataUrl: dataUrl,
        image: {
          source: "unsplash",
          url: photo.preview_url,
          storage_key: null,
          unsplash_id: photo.id,
          attribution: photo.attribution,
        },
      });
    } catch {
      if (epochRef.current !== epoch) return;
      setState((s) => ({ ...s, imageError: "Couldn’t load that photo. Try another." }));
    }
  }, []);

  /** Use an uploaded image (already stored server-side; `url` is auth-gated). */
  const selectUpload = useCallback(async (url: string, storageKey: string) => {
    const epoch = ++epochRef.current;
    try {
      const dataUrl = await fetchImageDataUrl(url);
      if (epochRef.current !== epoch) return;
      setState({
        imageError: null,
        imageDataUrl: dataUrl,
        image: { source: "upload", url, storage_key: storageKey, unsplash_id: null, attribution: null },
      });
    } catch {
      if (epochRef.current !== epoch) return;
      setState((s) => ({ ...s, imageError: "Couldn’t load the uploaded image." }));
    }
  }, []);

  const clearImage = useCallback(() => {
    epochRef.current += 1; // cancel any in-flight image fetch so it can't resurrect the image
    setState({ image: null, imageDataUrl: null, imageError: null });
  }, []);

  /** Seed an already-persisted image (History re-open) WITHOUT re-PATCHing it —
   *  only a *new* selection should PATCH. `genId` is passed explicitly because the
   *  caller sets it in the same render, before this hook re-reads `generationId`. */
  const hydrate = useCallback(async (genId: string, image: CardImage | null) => {
    const epoch = ++epochRef.current;
    persistedKeyRef.current = image ? `${genId}:${imageKey(image)}` : null;
    setState({ image, imageDataUrl: null, imageError: null });
    if (image?.url) {
      try {
        const dataUrl = await fetchImageDataUrl(image.url);
        if (epochRef.current === epoch) setState((s) => ({ ...s, imageDataUrl: dataUrl }));
      } catch {
        if (epochRef.current === epoch)
          setState((s) => ({ ...s, imageError: "Couldn’t load the image." }));
      }
    }
  }, []);

  const reset = useCallback(() => {
    epochRef.current += 1;
    persistedKeyRef.current = null;
    setState(EMPTY);
  }, []);

  // Persist the picked image onto the generation once both exist. Idempotent per
  // (generation, image) so we don't re-PATCH on every render. The server nests the
  // image under `output.card` for a post_pack; the PATCH body is identical.
  useEffect(() => {
    if (!workspaceId || !generationId || !state.image) return;
    const key = `${generationId}:${imageKey(state.image)}`;
    if (persistedKeyRef.current === key) return;
    persistedKeyRef.current = key;
    api
      .patch(`/workspaces/${workspaceId}/generations/${generationId}`, { image: state.image })
      .catch(() => {
        persistedKeyRef.current = null; // allow a retry on the next change
      });
  }, [workspaceId, generationId, state.image]);

  return { ...state, selectUnsplash, selectUpload, clearImage, hydrate, reset };
}
