import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Workspace } from "@/types";

export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: async () => (await api.get<Workspace[]>("/workspaces")).data,
    // The corpus-ready gate reads ready_chunk_count from here; keep it fresh on
    // navigation so it reflects ingestion that finished on another route.
    staleTime: 0,
  });
}

export function useWorkspace(workspaceId: string | null) {
  return useQuery({
    queryKey: ["workspace", workspaceId],
    enabled: !!workspaceId,
    queryFn: async () => (await api.get<Workspace>(`/workspaces/${workspaceId}`)).data,
  });
}

export interface CreateWorkspaceInput {
  name: string;
}

export function useCreateWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateWorkspaceInput) =>
      (await api.post<Workspace>("/workspaces", input)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspaces"] }),
  });
}
