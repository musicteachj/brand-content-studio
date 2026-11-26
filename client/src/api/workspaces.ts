import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { BrandExtract, BrandProfilePatch, CardTemplate, Workspace } from "@/types";

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

// PATCH merges partial updates server-side. `brand_profile` is REPLACED whole
// (not deep-merged) — send the full identity profile when editing it. The
// sub-collections are re-hydrated server-side (workspace_service.py), hence the
// Patch shape rather than the full BrandProfile.
export interface UpdateWorkspaceInput {
  name?: string;
  brand_profile?: BrandProfilePatch;
}

export function useUpdateWorkspace(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: UpdateWorkspaceInput) =>
      (await api.patch<Workspace>(`/workspaces/${workspaceId}`, input)).data,
    onSuccess: (ws) => {
      qc.invalidateQueries({ queryKey: ["workspace", ws.id] });
      qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useDeleteWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (workspaceId: string) => {
      await api.delete(`/workspaces/${workspaceId}`);
      return workspaceId;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspaces"] }),
  });
}

function invalidateWorkspace(qc: ReturnType<typeof useQueryClient>, ws: Workspace) {
  qc.invalidateQueries({ queryKey: ["workspace", ws.id] });
  qc.invalidateQueries({ queryKey: ["workspaces"] });
}

// Logo upload/delete use a targeted server-side update of brand_profile.logo
// (they never clobber the rest of the profile), so they persist immediately,
// separate from the brand-editor Save.
export function useUploadLogo(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return (await api.post<Workspace>(`/workspaces/${workspaceId}/logo`, form)).data;
    },
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useDeleteLogo(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.delete<Workspace>(`/workspaces/${workspaceId}/logo`)).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

// Phase 4c — propose a brand profile from an uploaded image. Returns a proposal
// only (no server-side mutation), so there's nothing to invalidate; the user
// reviews + applies it into the editor, which persists via the brand PATCH.
export function useExtractBrand(workspaceId: string | null) {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return (await api.post<BrandExtract>(`/workspaces/${workspaceId}/brand/extract`, form)).data;
    },
  });
}

// Phase 4c exemplar steering — upload a past brand card (the server extracts a
// style note and stores it on brand_profile.exemplars) / remove one.
export function useAddExemplar(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return (await api.post<Workspace>(`/workspaces/${workspaceId}/exemplars`, form)).data;
    },
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useRemoveExemplar(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (exemplarId: string) =>
      (await api.delete<Workspace>(`/workspaces/${workspaceId}/exemplars/${exemplarId}`)).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

// Brand-image library — save a reusable image (stored on brand_profile.brand_images,
// no model call) / remove one. Pickable later as a card image in the picker.
export function useAddBrandImage(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return (await api.post<Workspace>(`/workspaces/${workspaceId}/brand-images`, form)).data;
    },
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useRemoveBrandImage(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (imageId: string) =>
      (await api.delete<Workspace>(`/workspaces/${workspaceId}/brand-images/${imageId}`)).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useRenameBrandImage(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { imageId: string; name: string }) =>
      (
        await api.patch<Workspace>(`/workspaces/${workspaceId}/brand-images/${input.imageId}`, {
          name: input.name,
        })
      ).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useAddFont(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { file: File; name: string }) => {
      const form = new FormData();
      form.append("file", input.file);
      form.append("name", input.name);
      return (await api.post<Workspace>(`/workspaces/${workspaceId}/fonts`, form)).data;
    },
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useRemoveFont(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (fontId: string) =>
      (await api.delete<Workspace>(`/workspaces/${workspaceId}/fonts/${fontId}`)).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useAddCardPreset(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      name: string;
      template_id: CardTemplate;
      accent_hex: string | null;
    }) => (await api.post<Workspace>(`/workspaces/${workspaceId}/card-presets`, input)).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useRemoveCardPreset(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (presetId: string) =>
      (await api.delete<Workspace>(`/workspaces/${workspaceId}/card-presets/${presetId}`)).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}
