import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Generation, GenerationType } from "@/types";

export type HistoryFilter = "all" | GenerationType;

export function useGenerations(workspaceId: string | null, filter: HistoryFilter = "all") {
  return useQuery({
    queryKey: ["generations", workspaceId, filter],
    enabled: !!workspaceId,
    queryFn: async () =>
      (
        await api.get<Generation[]>(`/workspaces/${workspaceId}/generations`, {
          params: { type: filter },
        })
      ).data,
  });
}

export function useGeneration(workspaceId: string | null, generationId: string | null) {
  return useQuery({
    queryKey: ["generation", workspaceId, generationId],
    enabled: !!workspaceId && !!generationId,
    queryFn: async () =>
      (await api.get<Generation>(`/workspaces/${workspaceId}/generations/${generationId}`)).data,
  });
}

export function useDeleteGeneration(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (generationId: string) =>
      api.delete(`/workspaces/${workspaceId}/generations/${generationId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["generations", workspaceId] }),
  });
}
