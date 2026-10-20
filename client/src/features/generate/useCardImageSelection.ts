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
 *  persisted image from History, and PATCH the selection (or its removal) onto the
 *  generation once both an image and a generation id exist. Image selection is parallel to the copy
 *  stream, so this lives outside the streaming state: a picked image therefore
 *  survives a regenerate and re-attaches to the new generation id. */
export function useCardImageSelection(workspaceId: string | null, generationId: string | null) {
  const [state, setState] = useState<ImageState>(EMPTY);
  // Idempotency guard for the persist PATCH, keyed `${generationId}:${imageKey}`.
  const persistedKeyRef = useRef<string | null>(null);
  // Bumped on every hydrate/reset/workspace-switch so a slow fetchImageDataUrl
  // from a prior generation can't write its bytes into the current one.
  const epochRef = useRef(0);
  // Image PATCHes run one at a time, so a removal can't land before the pick it undoes.
  const patchQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  // While a removal is in flight the persist effect waits, so a re-pick or a
  // regenerate in that window is saved after it, never undone by it.
  const removingRef = useRef(false);
  const [removing, setRemoving] = useState(false);

  const patchImage = useCallback(
    (genId: string, image: CardImage | null) => {
      const url = `/workspaces/${workspaceId}/generations/${genId}`;
      const next = patchQueueRef.current.catch(() => {}).then(() => api.patch(url, { image }));
      patchQueueRef.current = next;
      return next;
    },
    [workspaceId],
  );

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
        image: {
          source: "upload",
          url,
          storage_key: storageKey,
          unsplash_id: null,
          attribution: null,
        },
      });
    } catch {
      if (epochRef.current !== epoch) return;
      setState((s) => ({ ...s, imageError: "Couldn’t load the uploaded image." }));
    }
  }, []);

  /** Remove the image, from the saved generation too (QA-07). With a generation,
   *  the card clears only once the server has, so a failure leaves the image in
   *  place with an error instead of letting it return on the next reload. */
  const clearImage = useCallback(() => {
    if (removingRef.current) return; // one removal at a time
    const epoch = ++epochRef.current; // cancel any in-flight image fetch so it can't resurrect the image
    if (!state.image) return;
    persistedKeyRef.current = null; // the server is about to have no image
    if (!workspaceId || !generationId) {
      setState(EMPTY);
      return;
    }
    removingRef.current = true;
    setRemoving(true);
    patchImage(generationId, null)
      .then(
        () => {
          // A pick made meanwhile wins (it saves once this settles); a regenerate
          // doesn't, so the image doesn't carry over to the new card.
          if (epochRef.current === epoch) setState(EMPTY);
        },
        () => {
          if (epochRef.current === epoch)
            setState((s) => ({ ...s, imageError: "Couldn’t remove the image. Try again." }));
        },
      )
      .finally(() => {
        removingRef.current = false;
        setRemoving(false);
      });
  }, [state.image, workspaceId, generationId, patchImage]);

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
    if (!workspaceId || !generationId || !state.image || removing) return;
    const key = `${generationId}:${imageKey(state.image)}`;
    if (persistedKeyRef.current === key) return;
    persistedKeyRef.current = key;
    patchImage(generationId, state.image).catch(() => {
      // Allow a retry on the next change, unless a newer PATCH already took over.
      if (persistedKeyRef.current === key) persistedKeyRef.current = null;
    });
  }, [workspaceId, generationId, state.image, removing, patchImage]);

  return { ...state, removing, selectUnsplash, selectUpload, clearImage, hydrate, reset };
}
