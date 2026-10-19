// Download a generated document file. The download route is JWT-auth-gated, so a
// plain anchor href won't work (no Authorization header), so fetch the bytes
// through the authed axios client and save the blob. No model call; the file was
// rendered at generation time and is just served back.
import { api } from "@/lib/api";
import { withJsonErrorBody } from "@/lib/apiError";
import type { DocumentArchetype, DocumentFormat } from "@/types";

export async function downloadDocumentFile(
  workspaceId: string,
  generationId: string,
  fmt: DocumentFormat,
  archetype: DocumentArchetype,
): Promise<void> {
  const res = await withJsonErrorBody(
    api.get<Blob>(`/workspaces/${workspaceId}/generations/${generationId}/download/${fmt}`, {
      responseType: "blob",
    }),
  );
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${archetype}.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
