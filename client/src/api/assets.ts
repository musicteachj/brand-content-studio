import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Asset, AssetKind, AssetPage } from "@/types";

const ASSETS_LIMIT = 30;

export function useAssets(workspaceId: string | null) {
  return useInfiniteQuery({
    queryKey: ["assets", workspaceId],
    enabled: !!workspaceId,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      (
        await api.get<AssetPage>(`/workspaces/${workspaceId}/assets`, {
          params: { limit: ASSETS_LIMIT, offset: pageParam },
        })
      ).data,
    getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
    // Poll while any loaded asset is still processing so the status pill flips
    // live (a just-uploaded asset sorts to the first page, so this catches it).
    refetchInterval: (query) =>
      query.state.data?.pages.some((p) => p.items.some((a) => a.ingestion_status === "processing"))
        ? 1500
        : false,
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
