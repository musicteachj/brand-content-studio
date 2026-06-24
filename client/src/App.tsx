import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ComingSoon } from "@/components/ComingSoon";
import { LoginPage } from "@/features/auth/LoginPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { AssetsPage } from "@/features/assets/AssetsPage";
import { GeneratePage } from "@/features/generate/GeneratePage";
import { HistoryPage } from "@/features/history/HistoryPage";
import { WorkspaceSetupPage } from "@/features/workspace-setup/WorkspaceSetupPage";
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
        <Route path="generate" element={<GeneratePage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="assets" element={<AssetsPage />} />
        <Route path="settings" element={<ComingSoon title="Settings" phase="Phase 1.5" />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
