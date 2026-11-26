import { AxiosError } from "axios";

const RATE_LIMITED = "Too many requests right now. Wait a minute and try again.";

/** The server's own message for a failed request, else `fallback`. Our API's
 *  4xx `detail` strings are written for users ("A font with that name exists.",
 *  "Templates may use {{placeholders}} only…") and say what to fix, so they
 *  beat a generic guess. A 429 without a `detail` is the per-IP rate limiter
 *  (which answers `{error: …}`), so it gets a rate-limit message rather than a
 *  fallback that blames the file. FastAPI's 422 validation errors carry a list,
 *  not a string, and network failures carry no response; both get the fallback. */
export function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof AxiosError) {
    const detail: unknown = err.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (err.response?.status === 429) return RATE_LIMITED;
  }
  return fallback;
}

/** For requests made with `responseType: "blob"` (file downloads): axios then
 *  hands back an error body as a Blob too, hiding the server's `detail`. Parse
 *  it back to JSON before rethrowing so `apiErrorMessage` can read it. */
export async function withJsonErrorBody<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (err) {
    const data: unknown = err instanceof AxiosError ? err.response?.data : undefined;
    if (err instanceof AxiosError && err.response && data instanceof Blob) {
      try {
        err.response.data = JSON.parse(await blobText(data));
      } catch {
        // Not JSON (e.g. a proxy's HTML error page): leave it; the fallback applies.
      }
    }
    throw err;
  }
}

function blobText(blob: Blob): Promise<string> {
  if (typeof blob.text === "function") return blob.text();
  // Older engines (and jsdom) lack Blob.text().
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}
