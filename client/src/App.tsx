import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/features/auth/LoginPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { AssetsPage } from "@/features/assets/AssetsPage";
import { ExamplesPage } from "@/features/examples/ExamplesPage";
import { GeneratePage } from "@/features/generate/GeneratePage";
import { HistoryPage } from "@/features/history/HistoryPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { StartPage } from "@/features/start/StartPage";
import { TemplatesPage } from "@/features/templates/TemplatesPage";
import { WorkspaceSetupPage } from "@/features/workspace-setup/WorkspaceSetupPage";
import { RequireWorkspace } from "@/features/workspace/RequireWorkspace";
import { useAuthStore } from "@/stores/auth";

/** The studio's routes need a session. Signed out, `/` is the start page and any other
 *  studio route (a deep link included) redirects to it. */
function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { pathname } = useLocation();
  if (isAuthenticated) return <>{children}</>;
  return pathname === "/" ? <StartPage /> : <Navigate to="/" replace />;
}

export default function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return (
    <Routes>
      {/* Public: the ready-made examples need no demo start and no bot check. */}
      <Route path="/examples" element={<ExamplesPage />} />
      {/* The development sign-in page; it sends visitors to `/` where password sign-in is closed. */}
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="setup" element={<WorkspaceSetupPage />} />
        <Route
          path="generate"
          element={
            <RequireWorkspace>
              <GeneratePage />
            </RequireWorkspace>
          }
        />
        <Route
          path="history"
          element={
            <RequireWorkspace>
              <HistoryPage />
            </RequireWorkspace>
          }
        />
        <Route
          path="assets"
          element={
            <RequireWorkspace>
              <AssetsPage />
            </RequireWorkspace>
          }
        />
        <Route
          path="templates"
          element={
            <RequireWorkspace>
              <TemplatesPage />
            </RequireWorkspace>
          }
        />
        <Route
          path="settings"
          element={
            <RequireWorkspace>
              <SettingsPage />
            </RequireWorkspace>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
