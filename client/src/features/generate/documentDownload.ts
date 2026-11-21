// Download a generated document file. A workspace's download route is JWT-auth-gated,
// so a plain anchor href won't work (no Authorization header): fetch the bytes through
// the axios client and save the blob. The public examples use the same path with their
// own URL. No model call; the file was rendered at generation time and is served back.
import { api } from "@/lib/api";
import { withJsonErrorBody } from "@/lib/apiError";
import type { DocumentArchetype, DocumentFormat } from "@/types";

/** Where a generation's file in `fmt` is downloaded from, relative to the API base. */
export type DocumentDownloadUrl = (fmt: DocumentFormat) => string;

/** The default: the signed-in workspace's download route. */
export function workspaceDownloadUrl(
  workspaceId: string,
  generationId: string,
): DocumentDownloadUrl {
  return (fmt) => `/workspaces/${workspaceId}/generations/${generationId}/download/${fmt}`;
}

export async function downloadDocumentFile(
  downloadUrl: DocumentDownloadUrl,
  fmt: DocumentFormat,
  archetype: DocumentArchetype,
): Promise<void> {
  const res = await withJsonErrorBody(api.get<Blob>(downloadUrl(fmt), { responseType: "blob" }));
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${archetype}.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
