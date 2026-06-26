import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { downloadBlob } from "@/features/generate/useCardExport";
import { api } from "@/lib/api";
import type { Template } from "@/types";

export function useTemplates(workspaceId: string | null) {
  return useQuery({
    queryKey: ["templates", workspaceId],
    enabled: !!workspaceId,
    queryFn: async () => (await api.get<Template[]>(`/workspaces/${workspaceId}/templates`)).data,
  });
}

export function useUploadTemplate(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return (await api.post<Template>(`/workspaces/${workspaceId}/templates`, form)).data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates", workspaceId] }),
  });
}

export function useDeleteTemplate(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (templateId: string) => {
      await api.delete(`/workspaces/${workspaceId}/templates/${templateId}`);
      return templateId;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates", workspaceId] }),
  });
}

export function useAiFillTemplate(workspaceId: string | null) {
  return useMutation({
    mutationFn: async (input: { templateId: string; brief: string }) =>
      (
        await api.post<{ values: Record<string, string> }>(
          `/workspaces/${workspaceId}/templates/${input.templateId}/ai-fill`,
          { brief: input.brief },
        )
      ).data.values,
  });
}

/** Render a template with values and trigger a file download. */
export async function renderTemplate(
  workspaceId: string,
  template: Template,
  values: Record<string, string>,
): Promise<void> {
  const resp = await api.post(
    `/workspaces/${workspaceId}/templates/${template.id}/render`,
    { values },
    { responseType: "blob" },
  );
  const base = template.name.replace(/\.(docx|pptx)$/i, "");
  downloadBlob(resp.data as Blob, `${base}-filled.${template.format}`);
}
