import { useEffect } from "react";
import { useWorkspaces } from "@/api/workspaces";
import { useWorkspaceStore } from "@/stores/workspace";
import type { Workspace } from "@/types";

/** Resolves the active workspace (Phase 4: multi-workspace). The persisted
 *  `activeId` wins when it still points at an existing workspace, so an explicit
 *  switch survives reload; we only fall back to the first workspace when nothing
 *  is chosen yet or the stored id is stale (e.g. after a delete), persisting that
 *  recovery so the UI and store stay in sync. */
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
