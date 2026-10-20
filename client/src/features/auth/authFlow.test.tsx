import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import App from "@/App";
import { LoginPage } from "@/features/auth/LoginPage";
import { api } from "@/lib/api";
import { useAuthStore, type AuthUser } from "@/stores/auth";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";

setupMswServer();

const DEMO_TOKEN = { access_token: "demo-token", token_type: "bearer", expires_in: 3600 };

function withProviders(ui: React.ReactElement, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.getState().logout();
});

describe("auth flow", () => {
  it("login stores the session and the interceptor attaches its token", async () => {
    let authHeader: string | null = null;
    server.use(
      http.get("*/api/auth/me", ({ request }) => {
        authHeader = request.headers.get("authorization");
        return HttpResponse.json<AuthUser>({
          id: "u1",
          email: "owner@example.com",
          full_name: "Owner",
          is_demo: false,
        });
      }),
    );

    withProviders(<LoginPage />);
    await userEvent.type(screen.getByLabelText(/email/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    // Sign-in sends the new token to /auth/me itself, then stores token + user together.
    await waitFor(() => expect(useAuthStore.getState().user?.email).toBe("owner@example.com"));
    expect(useAuthStore.getState().token).toBe("test-token");
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(authHeader).toBe("Bearer test-token");

    // Every later request gets the stored token from the interceptor.
    authHeader = null;
    await api.get("/auth/me");
    expect(authHeader).toBe("Bearer test-token");
  });

  it("an explicit Authorization header isn't replaced by the stored token", async () => {
    let authHeader: string | null = null;
    server.use(
      http.get("*/api/auth/me", ({ request }) => {
        authHeader = request.headers.get("authorization");
        return HttpResponse.json<AuthUser>({
          id: "u1",
          email: "owner@example.com",
          full_name: "Owner",
          is_demo: false,
        });
      }),
    );
    useAuthStore.setState({ token: "old-token" });

    await api.get("/auth/me", { headers: { Authorization: "Bearer new-token" } });
    expect(authHeader).toBe("Bearer new-token");
  });

  it("a 401 from an authenticated request logs out and redirects to login", async () => {
    useAuthStore.setState({
      token: "stale-token",
      isAuthenticated: true,
      user: { id: "u1", email: "owner@example.com", full_name: "Owner", is_demo: false },
    });
    // Every API call the authenticated shell makes comes back 401.
    server.use(http.all("*/api/*", () => new HttpResponse(null, { status: 401 })));

    withProviders(<App />, "/");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument(),
    );
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  // QA-02: a reload during /auth/me used to persist { isAuthenticated: true, user: null }.
  it("persists nothing and stays on sign-in until /auth/me returns", async () => {
    let releaseMe!: () => void;
    const meGate = new Promise<void>((resolve) => (releaseMe = resolve));
    let authHeader: string | null = null;
    server.use(
      http.post("*/api/auth/demo-login", () => HttpResponse.json(DEMO_TOKEN)),
      http.get("*/api/auth/me", async ({ request }) => {
        authHeader = request.headers.get("authorization");
        await meGate;
        return HttpResponse.json<AuthUser>({
          id: "d1",
          email: "demo@folio.studio",
          full_name: "Demo Visitor",
          is_demo: true,
        });
      }),
    );

    const { unmount } = withProviders(<App />, "/login");
    await userEvent.click(screen.getByRole("button", { name: /explore as demo/i }));
    await waitFor(() => expect(authHeader).toBe("Bearer demo-token"));

    // /auth/me is in flight: a reload now must find no session.
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().token).toBeNull();
    expect(localStorage.getItem("folio-auth") ?? "").not.toContain("demo-token");
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    // A second sign-in can't start and race this one for the session.
    expect(screen.getByRole("button", { name: /^sign in$/i })).toBeDisabled();

    // Stop at the sign-in step: the shell it redirects to isn't under test here.
    unmount();
    releaseMe();
    await waitFor(() => expect(useAuthStore.getState().user?.is_demo).toBe(true));
    expect(useAuthStore.getState().token).toBe("demo-token");
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it("a failed /auth/me leaves the visitor signed out", async () => {
    server.use(
      http.post("*/api/auth/demo-login", () => HttpResponse.json(DEMO_TOKEN)),
      http.get("*/api/auth/me", () => new HttpResponse(null, { status: 500 })),
    );

    withProviders(<App />, "/login");
    await userEvent.click(screen.getByRole("button", { name: /explore as demo/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().token).toBeNull();
    expect(localStorage.getItem("folio-auth") ?? "").not.toContain("demo-token");
  });
});
