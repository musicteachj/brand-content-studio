import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Asset, AssetKind } from "@/types";

export function useAssets(workspaceId: string | null) {
  return useQuery({
    queryKey: ["assets", workspaceId],
    enabled: !!workspaceId,
    queryFn: async () => (await api.get<Asset[]>(`/workspaces/${workspaceId}/assets`)).data,
    // Poll while anything is still processing so the status pill flips live.
    refetchInterval: (query) => {
      const data = query.state.data as Asset[] | undefined;
      return data?.some((a) => a.ingestion_status === "processing") ? 1500 : false;
    },
  });
}

export interface UploadAssetInput {
  file: File;
  assetKind: AssetKind;
}

export function useUploadAsset(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, assetKind }: UploadAssetInput) => {
      const form = new FormData();
      form.append("file", file);
      form.append("asset_kind", assetKind);
      return (
        await api.post<Asset>(`/workspaces/${workspaceId}/assets`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
      ).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["assets", workspaceId] });
      qc.invalidateQueries({ queryKey: ["workspace", workspaceId] });
      // The active-workspace gate (corpus-ready) reads from the workspaces list.
      qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useDeleteAsset(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (assetId: string) =>
      api.delete(`/workspaces/${workspaceId}/assets/${assetId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["assets", workspaceId] });
      qc.invalidateQueries({ queryKey: ["workspace", workspaceId] });
      // The active-workspace gate (corpus-ready) reads from the workspaces list.
      qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}
