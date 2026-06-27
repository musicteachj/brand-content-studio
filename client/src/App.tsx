import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/features/auth/LoginPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { AssetsPage } from "@/features/assets/AssetsPage";
import { GeneratePage } from "@/features/generate/GeneratePage";
import { HistoryPage } from "@/features/history/HistoryPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { TemplatesPage } from "@/features/templates/TemplatesPage";
import { WorkspaceSetupPage } from "@/features/workspace-setup/WorkspaceSetupPage";
import { RequireWorkspace } from "@/features/workspace/RequireWorkspace";
import { useAuthStore } from "@/stores/auth";

function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return (
    <Routes>
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
