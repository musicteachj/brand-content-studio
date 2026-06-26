import { Check, ChevronsUpDown, Plus, Settings2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

/** TopBar workspace switcher (Phase 4a). Lists the owner's workspaces, switches
 *  the active one (persisted via the store), and routes to create/manage. */
export function WorkspaceSwitcher() {
  const navigate = useNavigate();
  const { workspace, workspaces } = useActiveWorkspace();
  const setActive = useWorkspaceStore((s) => s.setActive);
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-surface-variant focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Switch workspace"
      >
        <span className="flex flex-col leading-none">
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Workspace
          </span>
          <span className="mt-1 text-sm font-medium text-foreground">
            {workspace?.name ?? "No workspace"}
          </span>
        </span>
        <ChevronsUpDown className="h-4 w-4 text-muted-foreground" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
        {workspaces.map((ws) => {
          const active = ws.id === workspace?.id;
          return (
            <DropdownMenuItem key={ws.id} onSelect={() => setActive(ws.id)} aria-current={active}>
              <Check
                className={cn("h-4 w-4 shrink-0", active ? "opacity-100" : "opacity-0")}
                aria-hidden
              />
              <span className="truncate">{ws.name}</span>
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => navigate("/setup")}
          disabled={isDemo}
          title={isDemo ? "Disabled in the demo" : undefined}
        >
          <Plus className="h-4 w-4 shrink-0" aria-hidden />
          New workspace
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/settings#workspaces")}>
          <Settings2 className="h-4 w-4 shrink-0" aria-hidden />
          Manage workspaces
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
