import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";

/** Gate for workspace-dependent pages: a signed-in owner with no workspaces is
 *  sent to the setup stepper instead of a dead-end, null-keyed page. The
 *  Dashboard and /setup stay ungated. `hasNone` is already `!isLoading &&
 *  !isError`, so this never redirects mid-fetch or on a server error. */
export function RequireWorkspace({ children }: { children: ReactNode }) {
  const { hasNone } = useActiveWorkspace();
  return hasNone ? <Navigate to="/setup" replace /> : <>{children}</>;
}
