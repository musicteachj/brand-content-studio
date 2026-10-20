import { useRef, useState, type RefObject } from "react";
import { Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useDeleteWorkspace, useUpdateWorkspace, useWorkspaces } from "@/api/workspaces";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { apiErrorMessage } from "@/lib/apiError";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";
import type { Workspace } from "@/types";

/** Settings → Workspaces (Phase 4a): list, rename, and delete the owner's
 *  workspaces. Create routes to the existing /setup stepper. Rename/delete are
 *  disabled for the demo user (the server also 403s via require_not_demo). */
export function WorkspacesSection() {
  const navigate = useNavigate();
  const { data: workspaces } = useWorkspaces();
  const { workspace: active } = useActiveWorkspace();
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  // Where focus goes after a confirmed delete removes its row.
  const newButtonRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col divide-y divide-border rounded-xl border border-border bg-surface shadow-light">
        {(workspaces ?? []).map((ws) => (
          <WorkspaceRow
            key={ws.id}
            ws={ws}
            isActive={ws.id === active?.id}
            isDemo={isDemo}
            canDelete={(workspaces?.length ?? 0) > 1}
            focusAfterDelete={newButtonRef}
          />
        ))}
      </div>
      <div>
        <Button
          ref={newButtonRef}
          variant="secondary"
          size="sm"
          onClick={() => navigate("/setup")}
          disabled={isDemo}
          title={isDemo ? "Disabled in the demo" : undefined}
        >
          <Plus className="h-4 w-4" aria-hidden />
          New workspace
        </Button>
      </div>
    </div>
  );
}

function WorkspaceRow({
  ws,
  isActive,
  isDemo,
  canDelete,
  focusAfterDelete,
}: {
  ws: Workspace;
  isActive: boolean;
  isDemo: boolean;
  canDelete: boolean;
  focusAfterDelete: RefObject<HTMLElement | null>;
}) {
  const setActive = useWorkspaceStore((s) => s.setActive);
  const update = useUpdateWorkspace(ws.id);
  const del = useDeleteWorkspace();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(ws.name);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const trimmed = name.trim();
    if (!trimmed || trimmed === ws.name) {
      setEditing(false);
      setName(ws.name);
      return;
    }
    setError(null);
    try {
      await update.mutateAsync({ name: trimmed });
      setEditing(false);
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn’t rename. Try again."));
    }
  }

  async function remove() {
    await del.mutateAsync(ws.id); // a failure shows in the confirm dialog
    if (isActive) setActive(null); // resolver falls back to the first workspace
  }

  return (
    <div className="flex items-center gap-3 px-4 py-3">
      {editing ? (
        <>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            aria-label="Workspace name"
            onKeyDown={(e) => {
              if (e.key === "Enter") void save();
              if (e.key === "Escape") {
                setEditing(false);
                setName(ws.name);
              }
            }}
            className="h-9 max-w-xs"
          />
          <div className="ml-auto flex items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              onClick={() => void save()}
              loading={update.isPending}
              aria-label="Save name"
            >
              <Check className="h-4 w-4" aria-hidden />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => {
                setEditing(false);
                setName(ws.name);
              }}
              aria-label="Cancel rename"
            >
              <X className="h-4 w-4" aria-hidden />
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="flex items-center gap-2 truncate text-sm font-medium text-foreground">
              {ws.name}
              {isActive && (
                <span className="rounded-full bg-surface-variant px-2 py-0.5 eyebrow text-3xs">
                  Active
                </span>
              )}
            </span>
            <span className="eyebrow">
              {ws.asset_count} asset{ws.asset_count === 1 ? "" : "s"}
            </span>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              onClick={() => setEditing(true)}
              disabled={isDemo}
              title={isDemo ? "Disabled in the demo" : "Rename"}
              aria-label="Rename workspace"
            >
              <Pencil className="h-4 w-4" aria-hidden />
            </Button>
            <ConfirmDialog
              trigger={
                <Button
                  size="icon"
                  variant="ghost"
                  disabled={isDemo || !canDelete}
                  title={
                    isDemo
                      ? "Disabled in the demo"
                      : !canDelete
                        ? "Keep at least one workspace"
                        : "Delete"
                  }
                  aria-label="Delete workspace"
                  className={cn(!isDemo && canDelete && "hover:text-destructive")}
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </Button>
              }
              title={`Delete “${ws.name}”?`}
              description="This permanently removes the workspace and all of its assets and generations. This can’t be undone."
              confirmLabel="Delete workspace"
              onConfirm={remove}
              errorFallback="Couldn’t delete. Try again."
              focusAfterConfirm={focusAfterDelete}
            />
          </div>
        </>
      )}
      {error && (
        <span role="alert" className="text-xs text-destructive">
          {error}
        </span>
      )}
    </div>
  );
}
