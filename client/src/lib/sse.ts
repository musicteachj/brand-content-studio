// SSE reader for streaming generation. Uses fetch + ReadableStream (NOT
// EventSource) so we can send a POST body and the JWT auth header
// (ARCHITECTURE gotcha #3). Decodes the EMS frame shape: `data: {json}\n\n`
// terminated by `data: [DONE]`. Text and card generation share this reader and
// frame shape (gotcha #3); only the terminal `meta` payload differs.
import { useAuthStore } from "@/stores/auth";
import type { SSECardMetaFrame, SSEDocumentMetaFrame, SSEMetaFrame, SSETextFrame } from "@/types";

/** Abort the read if no frame arrives within this window: a stalled stream
 *  (proxy hang, dropped connection) should surface an error, not spin forever. */
export const STREAM_INACTIVITY_MS = 30000;

export interface StreamHandlers<Meta> {
  onText: (text: string) => void;
  onMeta: (meta: Meta) => void;
  onError: (message: string) => void;
}

export interface TextStreamBody {
  brief: string;
  tone: string;
  length: string;
}

export interface CardStreamBody {
  brief: string;
  template_id: string;
  tone: string;
}

export interface DocumentStreamBody {
  brief: string;
  archetype: string;
  tone: string;
}

export interface PostPackStreamBody {
  brief: string;
  tone: string;
  template_id: string;
}

/** POST a streaming request with the JWT + JSON body. Returns the Response, or
 *  null after invoking `onError` (network failure, non-OK status, no body). */
async function openStream(
  url: string,
  body: unknown,
  onError: (message: string) => void,
  signal?: AbortSignal,
): Promise<Response | null> {
  const token = useAuthStore.getState().token;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return null;
    onError("Network error. Is the server running?");
    return null;
  }

  if (!response.ok) {
    // Non-stream error (e.g. 409 empty corpus). Body is JSON {detail}.
    let detail = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* ignore */
    }
    onError(detail);
    return null;
  }

  if (!response.body) {
    onError("Streaming is not supported in this environment.");
    return null;
  }
  return response;
}

/** Read decoded SSE frames until `[DONE]`, the stream ends, it is aborted, or it
 *  stalls past STREAM_INACTIVITY_MS (each `read()` races an inactivity timer). */
export async function readFrames<Meta>(
  response: Response,
  handlers: StreamHandlers<Meta>,
): Promise<void> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      let timer: ReturnType<typeof setTimeout>;
      const timeout = new Promise<"timeout">((resolve) => {
        timer = setTimeout(() => resolve("timeout"), STREAM_INACTIVITY_MS);
      });
      let result: Awaited<ReturnType<typeof reader.read>> | "timeout";
      try {
        result = await Promise.race([reader.read(), timeout]);
      } finally {
        clearTimeout(timer!);
      }
      if (result === "timeout") {
        await reader.cancel();
        handlers.onError("The stream stalled. Try again.");
        return;
      }
      const { done, value } = result;
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Frames are separated by a blank line (tolerate CRLF from proxies).
      const boundary = /\r?\n\r?\n/;
      let match: RegExpExecArray | null;
      while ((match = boundary.exec(buffer)) !== null) {
        const rawFrame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        const line = rawFrame.replace(/^data:\s?/, "").replace(/\r$/, "");
        if (line === "[DONE]") return;
        if (!line) continue;
        try {
          const payload = JSON.parse(line);
          if ("text" in payload) handlers.onText((payload as SSETextFrame).text);
          else if ("meta" in payload) handlers.onMeta((payload as { meta: Meta }).meta);
          else if ("error" in payload)
            handlers.onError(
              typeof payload.error === "string" ? payload.error : "Generation failed.",
            );
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") handlers.onError("Stream interrupted.");
  } finally {
    reader.releaseLock();
  }
}

/** Stream a text-post generation. Resolves on [DONE], error, or abort. */
export async function streamTextGeneration(
  workspaceId: string,
  body: TextStreamBody,
  handlers: StreamHandlers<SSEMetaFrame["meta"]>,
  signal?: AbortSignal,
): Promise<void> {
  const response = await openStream(
    `/api/workspaces/${workspaceId}/generate/text`,
    body,
    handlers.onError,
    signal,
  );
  if (response) await readFrames(response, handlers);
}

/** Stream an image-card generation: copy streams as text, the terminal meta
 *  carries the structured fields + image keywords. */
export async function streamCardGeneration(
  workspaceId: string,
  body: CardStreamBody,
  handlers: StreamHandlers<SSECardMetaFrame["meta"]>,
  signal?: AbortSignal,
): Promise<void> {
  const response = await openStream(
    `/api/workspaces/${workspaceId}/generate/card`,
    body,
    handlers.onError,
    signal,
  );
  if (response) await readFrames(response, handlers);
}

/** Stream the "LinkedIn Post" objective: the caption streams as text, the
 *  terminal meta carries the distilled card fields + image keywords (same meta
 *  shape as a card). */
export async function streamPostPackGeneration(
  workspaceId: string,
  body: PostPackStreamBody,
  handlers: StreamHandlers<SSECardMetaFrame["meta"]>,
  signal?: AbortSignal,
): Promise<void> {
  const response = await openStream(
    `/api/workspaces/${workspaceId}/generate/post`,
    body,
    handlers.onError,
    signal,
  );
  if (response) await readFrames(response, handlers);
}

/** Stream a document generation: the draft streams as text, the terminal meta
 *  carries the structured model + the per-format storage keys. */
export async function streamDocumentGeneration(
  workspaceId: string,
  body: DocumentStreamBody,
  handlers: StreamHandlers<SSEDocumentMetaFrame["meta"]>,
  signal?: AbortSignal,
): Promise<void> {
  const response = await openStream(
    `/api/workspaces/${workspaceId}/generate/document`,
    body,
    handlers.onError,
    signal,
  );
  if (response) await readFrames(response, handlers);
}
