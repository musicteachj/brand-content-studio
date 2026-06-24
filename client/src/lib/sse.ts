// SSE reader for streaming generation. Uses fetch + ReadableStream (NOT
// EventSource) so we can send a POST body and the JWT auth header
// (ARCHITECTURE gotcha #3). Decodes the EMS frame shape: `data: {json}\n\n`
// terminated by `data: [DONE]`.
import { useAuthStore } from "@/stores/auth";
import type { SSEMetaFrame, SSETextFrame } from "@/types";

export interface StreamHandlers {
  onText: (text: string) => void;
  onMeta: (meta: SSEMetaFrame["meta"]) => void;
  onError: (message: string) => void;
}

export interface TextStreamBody {
  brief: string;
  tone: string;
  length: string;
}

/** Stream a text-post generation. Returns when the stream completes ([DONE]),
 *  errors, or is aborted. */
export async function streamTextGeneration(
  workspaceId: string,
  body: TextStreamBody,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = useAuthStore.getState().token;
  let response: Response;
  try {
    response = await fetch(`/api/workspaces/${workspaceId}/generate/text`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    handlers.onError("Network error — is the server running?");
    return;
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
    handlers.onError(detail);
    return;
  }

  if (!response.body) {
    handlers.onError("Streaming is not supported in this environment.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
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
          else if ("meta" in payload) handlers.onMeta((payload as SSEMetaFrame).meta);
          else if ("error" in payload) handlers.onError(payload.error);
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
