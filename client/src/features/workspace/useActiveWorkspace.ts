import { useEffect } from "react";
import { useWorkspaces } from "@/api/workspaces";
import { useWorkspaceStore } from "@/stores/workspace";
import type { Workspace } from "@/types";

/** Resolves the active workspace, auto-selecting the first one when none is
 *  chosen yet (Phase 1a is single-workspace per user). */
export function useActiveWorkspace() {
  const { data: workspaces, isLoading, isError } = useWorkspaces();
  const activeId = useWorkspaceStore((s) => s.activeId);
  const setActive = useWorkspaceStore((s) => s.setActive);

  const resolved: Workspace | undefined =
    workspaces?.find((w) => w.id === activeId) ?? workspaces?.[0];

  useEffect(() => {
    if (resolved && resolved.id !== activeId) setActive(resolved.id);
  }, [resolved, activeId, setActive]);

  return {
    workspace: resolved,
    workspaceId: resolved?.id ?? null,
    workspaces: workspaces ?? [],
    isLoading,
    isError,
    hasNone: !isLoading && !isError && (workspaces?.length ?? 0) === 0,
  };
}
