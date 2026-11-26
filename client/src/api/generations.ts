import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Generation, GenerationPage, GenerationType } from "@/types";

export type HistoryFilter = "all" | GenerationType;

const HISTORY_LIMIT = 24;

export function useGenerations(workspaceId: string | null, filter: HistoryFilter = "all") {
  return useInfiniteQuery({
    queryKey: ["generations", workspaceId, filter],
    enabled: !!workspaceId,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      (
        await api.get<GenerationPage>(`/workspaces/${workspaceId}/generations`, {
          params: { type: filter, limit: HISTORY_LIMIT, offset: pageParam },
        })
      ).data,
    getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
  });
}

export function useGenerationCount(workspaceId: string | null) {
  return useQuery({
    queryKey: ["generations-count", workspaceId],
    enabled: !!workspaceId,
    queryFn: async () =>
      (await api.get<{ count: number }>(`/workspaces/${workspaceId}/generations/count`)).data.count,
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["generations", workspaceId] });
      qc.invalidateQueries({ queryKey: ["generations-count", workspaceId] });
    },
  });
}
