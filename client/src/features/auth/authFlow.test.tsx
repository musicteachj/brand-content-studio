import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import App from "@/App";
import { LoginPage } from "@/features/auth/LoginPage";
import { useAuthStore } from "@/stores/auth";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";

setupMswServer();

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
  it("login stores the token and attaches it to the next request", async () => {
    let authHeader: string | null = null;
    server.use(
      http.get("*/api/auth/me", ({ request }) => {
        authHeader = request.headers.get("authorization");
        return HttpResponse.json({
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

    // /auth/me runs only after the token is set, so waiting on the user proves the
    // whole chain: login → token stored → interceptor attached it to /auth/me.
    await waitFor(() => expect(useAuthStore.getState().user?.email).toBe("owner@example.com"));
    expect(useAuthStore.getState().token).toBe("test-token");
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(authHeader).toBe("Bearer test-token");
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
});
