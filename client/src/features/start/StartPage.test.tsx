import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { appStatusQuery, LIVE_AI_PAUSED_COPY, type AppStatus } from "@/api/status";
import { useAuthStore, type AuthUser } from "@/stores/auth";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";

// Cloudflare's script never loads in jsdom: every demo start gets the token "tok".
const turnstileCalls: { slot: HTMLElement; siteKey: string }[] = [];
vi.mock("@/lib/turnstile", () => ({
  getTurnstileToken: async (slot: HTMLElement, siteKey: string) => {
    turnstileCalls.push({ slot, siteKey });
    return "tok";
  },
}));
// The signed-in shell makes its own requests and has its own tests; a stand-in shows
// that the visitor landed on it.
vi.mock("@/components/layout/AppShell", () => ({
  AppShell: () => <p>Studio dashboard</p>,
}));

setupMswServer();

const DEV_STATUS: AppStatus = {
  live_ai_available: true,
  live_ai_reason: "available",
  turnstile_site_key: "1x00000000000000000000AA",
  password_login: true,
};
const PROD_STATUS: AppStatus = { ...DEV_STATUS, password_login: false };

/** The app at `route`, signed out. `status` is what GET /api/status answers; it is also
 *  in the cache from the start, so a test can assert on a page that has already read it. */
function renderApp(route = "/", status: AppStatus = DEV_STATUS) {
  server.use(http.get("*/api/status", () => HttpResponse.json<AppStatus>(status)));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(appStatusQuery.queryKey, status);
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.getState().logout();
  turnstileCalls.length = 0;
});

describe("StartPage", () => {
  it("offers the live demo and the examples side by side", async () => {
    renderApp();

    const live = await screen.findByRole("button", { name: "Try it live" });
    const examples = screen.getByRole("link", { name: "See ready-made examples" });
    expect(examples).toHaveAttribute("href", "/examples");
    expect(live.parentElement).toBe(examples.parentElement);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    // Nothing is checked until the visitor asks for the live demo.
    expect(turnstileCalls).toHaveLength(0);
  });

  it("shows the studio in four described screenshots", async () => {
    renderApp();
    await screen.findByRole("button", { name: "Try it live" });
    const shots = screen.getAllByRole("img").filter((img) => img.tagName === "IMG");
    expect(shots.map((img) => img.getAttribute("src"))).toEqual([
      "/screenshots/linkedin-post.jpg",
      "/screenshots/image-card.jpg",
      "/screenshots/document.jpg",
      "/screenshots/retrieved-context.jpg",
    ]);
    for (const img of shots) expect(img.getAttribute("alt")!.length).toBeGreaterThan(40);
  });

  it("says live generation is paused before the bot check when the status says so", async () => {
    renderApp("/", { ...DEV_STATUS, live_ai_available: false, live_ai_reason: "paused" });

    const notice = await screen.findByText(LIVE_AI_PAUSED_COPY);
    const start = screen.getByRole("button", { name: "Explore the studio" });
    expect(screen.queryByRole("button", { name: "Try it live" })).not.toBeInTheDocument();
    // The notice comes before the button, and before any bot check.
    expect(notice.compareDocumentPosition(start) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(turnstileCalls).toHaveLength(0);
    expect(screen.getByRole("link", { name: "See ready-made examples" })).toBeInTheDocument();
  });

  it("starts a demo with a Turnstile token and lands on the dashboard", async () => {
    let body: unknown = null;
    server.use(
      http.post("*/api/auth/demo-login", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ access_token: "demo-token", token_type: "bearer" });
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
    renderApp();

    await userEvent.click(await screen.findByRole("button", { name: "Try it live" }));

    expect(await screen.findByText("Studio dashboard")).toBeInTheDocument();
    expect(body).toEqual({ turnstile_token: "tok" });
    expect(turnstileCalls).toHaveLength(1);
    expect(turnstileCalls[0]!.siteKey).toBe(DEV_STATUS.turnstile_site_key);
    expect(useAuthStore.getState().token).toBe("demo-token");
  });

  it("shows the server's refusal text when the bot check fails", async () => {
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
    renderApp();

    await userEvent.click(await screen.findByRole("button", { name: "Try it live" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We couldn't confirm you're a person. Please try again.",
    );
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    // The free path stays open.
    expect(screen.getByRole("link", { name: "See ready-made examples" })).toBeInTheDocument();
  });

  it("never shows the password form in production", async () => {
    renderApp("/", PROD_STATUS);
    expect(await screen.findByRole("button", { name: "Try it live" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^sign in$/i })).not.toBeInTheDocument();
  });

  it("shows the password form in development and signs in with it", async () => {
    renderApp();
    await userEvent.type(await screen.findByLabelText("Email"), "owner@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByText("Studio dashboard")).toBeInTheDocument();
    expect(useAuthStore.getState().token).toBe("test-token");
  });

  it("sends the sign-in page to the start page when password sign-in is closed", async () => {
    renderApp("/login", PROD_STATUS);
    expect(await screen.findByRole("button", { name: "Try it live" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
  });

  it("sends a signed-out deep link back to the start page", async () => {
    renderApp("/history");
    expect(await screen.findByRole("button", { name: "Try it live" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Studio dashboard")).not.toBeInTheDocument());
  });
});
