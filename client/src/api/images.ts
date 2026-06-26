import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import type { ImageUploadResponse, UnsplashSearchResponse } from "@/types";

/** Unsplash search proxy. Disabled until a query is present so we don't burn the
 *  rate limit on an empty box. */
export function useUnsplashSearch(query: string, page = 1) {
  const q = query.trim();
  return useQuery({
    queryKey: ["unsplash", q, page],
    enabled: q.length > 0,
    staleTime: 5 * 60_000,
    queryFn: async () =>
      (
        await api.get<UnsplashSearchResponse>("/images/unsplash/search", {
          params: { q, page },
        })
      ).data,
  });
}

/** Fire Unsplash's download-tracking endpoint on selection (license requirement).
 *  Best-effort — never blocks selection. */
export async function trackUnsplashDownload(downloadLocation: string): Promise<void> {
  if (!downloadLocation) return;
  try {
    await api.post("/images/unsplash/track", { download_location: downloadLocation });
  } catch {
    /* best-effort */
  }
}

export async function uploadImage(workspaceId: string, file: File): Promise<ImageUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<ImageUploadResponse>(
    `/workspaces/${workspaceId}/images/upload`,
    form,
  );
  return data;
}

/** Fetch image bytes as a data URL. Uploaded-image URLs are same-origin and
 *  auth-gated, so a bare <img src> (which can't carry the JWT) 401s — fetch with
 *  the bearer token. A data URL works everywhere the card is rendered: the DOM
 *  live preview, the Satori locked preview, and the resvg PNG export (Satori/resvg
 *  can't resolve a blob: or cross-origin URL during rasterization). Remote
 *  (Unsplash) URLs are fetched without auth. */
export async function fetchImageDataUrl(url: string): Promise<string> {
  // Same-origin = a leading single slash. A protocol-relative `//host` must NOT
  // count, or the bearer token would be sent cross-origin.
  const sameOrigin = url.startsWith("/") && !url.startsWith("//");
  const token = useAuthStore.getState().token;
  const resp = await fetch(url, {
    headers: sameOrigin && token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`Image fetch failed (${resp.status})`);
  const blob = await resp.blob();
  return await new Promise<string>((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result as string);
    fr.onerror = () => reject(fr.error);
    fr.readAsDataURL(blob);
  });
}
