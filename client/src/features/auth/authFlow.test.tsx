import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import type { AppStatus } from "@/api/status";
import { LoginPage } from "@/features/auth/LoginPage";
import { api } from "@/lib/api";
import { useAuthStore, type AuthUser } from "@/stores/auth";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";

// Cloudflare's script never loads in jsdom: every demo start here gets the token "tok", and
// records what it was asked for.
const turnstileCalls: { slot: HTMLElement; siteKey: string }[] = [];
vi.mock("@/lib/turnstile", () => ({
  getTurnstileToken: async (slot: HTMLElement, siteKey: string) => {
    turnstileCalls.push({ slot, siteKey });
    return "tok";
  },
}));

setupMswServer();

const DEV_STATUS: AppStatus = {
  live_ai_available: true,
  live_ai_reason: "available",
  turnstile_site_key: "1x00000000000000000000AA",
  password_login: true,
};

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
  turnstileCalls.length = 0;
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
    await userEvent.type(await screen.findByLabelText(/email/i), "owner@example.com");
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

  it("a 401 from an authenticated request logs out and returns to the start page", async () => {
    useAuthStore.setState({
      token: "stale-token",
      isAuthenticated: true,
      user: { id: "u1", email: "owner@example.com", full_name: "Owner", is_demo: false },
    });
    // Every API call the authenticated shell makes comes back 401.
    server.use(http.all("*/api/*", () => new HttpResponse(null, { status: 401 })));

    withProviders(<App />, "/");

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Try it live" })).toBeInTheDocument(),
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

  it("sends the Turnstile token with the demo start", async () => {
    let body: unknown = null;
    server.use(
      http.get("*/api/status", () =>
        HttpResponse.json<AppStatus>({ ...DEV_STATUS, turnstile_site_key: "0x4AAAAAAAsite" }),
      ),
      http.post("*/api/auth/demo-login", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(DEMO_TOKEN);
      }),
      http.get("*/api/auth/me", () =>
        HttpResponse.json<AuthUser>({
          id: "d1",
          email: "demo@folio.studio",
          full_name: "Demo Visitor",
          is_demo: true,
        }),
      ),
    );

    withProviders(<LoginPage />);
    await userEvent.click(screen.getByRole("button", { name: /explore as demo/i }));

    await waitFor(() => expect(useAuthStore.getState().user?.is_demo).toBe(true));
    expect(body).toEqual({ turnstile_token: "tok" });
    // One widget, in the slot under the button, with the server's site key.
    expect(turnstileCalls).toHaveLength(1);
    expect(turnstileCalls[0]!.siteKey).toBe("0x4AAAAAAAsite");
    expect(turnstileCalls[0]!.slot).toBeInstanceOf(HTMLElement);
    expect(turnstileCalls[0]!.slot.isConnected).toBe(true);
  });

  it("shows the server's refusal when the bot check fails", async () => {
    server.use(
      http.post("*/api/auth/demo-login", () =>
        HttpResponse.json(
          {
            detail: "We couldn't confirm you're a person. Please try again.",
            code: "bot_check_failed",
          },
          { status: 403 },
        ),
      ),
    );

    withProviders(<LoginPage />);
    await userEvent.click(screen.getByRole("button", { name: /explore as demo/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We couldn't confirm you're a person. Please try again.",
    );
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("a failed demo start says so in plain words", async () => {
    server.use(http.post("*/api/auth/demo-login", () => HttpResponse.error()));

    withProviders(<LoginPage />);
    await userEvent.click(screen.getByRole("button", { name: /explore as demo/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The demo couldn't start. Try again in a moment.");
    expect(alert).not.toHaveTextContent(/server running/i);
  });

  it("sends visitors to the start page when password sign-in is closed", async () => {
    server.use(
      http.get("*/api/status", () =>
        HttpResponse.json<AppStatus>({ ...DEV_STATUS, password_login: false }),
      ),
    );

    withProviders(<App />, "/login");

    expect(await screen.findByRole("button", { name: "Try it live" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /explore as demo/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^sign in$/i })).not.toBeInTheDocument();
  });

  it("shows the password sign-in when the server allows it", async () => {
    withProviders(<LoginPage />);
    expect(await screen.findByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^sign in$/i })).toBeInTheDocument();
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
