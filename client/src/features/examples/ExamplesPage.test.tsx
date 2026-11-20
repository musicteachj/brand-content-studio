import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { useAuthStore } from "@/stores/auth";
import { EXAMPLES } from "@/test/msw/handlers";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";
import type { ExamplesResponse } from "@/types";

setupMswServer();

function renderExamples() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/examples"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.getState().logout();
  // Card thumbnails size themselves with a ResizeObserver, which jsdom lacks.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ExamplesPage", () => {
  it("lists the four examples without signing in", async () => {
    const authHeaders: (string | null)[] = [];
    server.use(
      http.get("*/api/examples", ({ request }) => {
        authHeaders.push(request.headers.get("authorization"));
        return HttpResponse.json<ExamplesResponse>(EXAMPLES);
      }),
    );
    renderExamples();

    for (const item of EXAMPLES.items) {
      expect(await screen.findByText(item.brief)).toBeInTheDocument();
    }
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Verdure Materials");
    expect(authHeaders.length).toBeGreaterThan(0);
    expect(authHeaders.every((h) => h === null)).toBe(true);
    // The way back to the live demo is the start page, where the bot check runs.
    expect(screen.getByRole("link", { name: /try it live/i })).toHaveAttribute("href", "/");
  });

  it("marks every item as an example and offers no edit or delete", async () => {
    renderExamples();
    await screen.findByText(EXAMPLES.items[0]!.brief);

    expect(screen.getAllByText("Example")).toHaveLength(4);
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /customize|edit/i })).not.toBeInTheDocument();

    // The detail view is read-only too: the brand sources, no edit or delete.
    await userEvent.click(screen.getByRole("button", { name: /statement card/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: /download png/i })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /customize/i })).not.toBeInTheDocument();
  });

  it("downloads a document example from the public URL", async () => {
    // jsdom has no object URLs or anchor navigation.
    globalThis.URL.createObjectURL = vi.fn(() => "blob:mock");
    globalThis.URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const requests: { path: string; auth: string | null }[] = [];
    server.use(
      http.get("*/api/examples/:generationId/download/:fmt", ({ request }) => {
        requests.push({
          path: new URL(request.url).pathname,
          auth: request.headers.get("authorization"),
        });
        return new HttpResponse(new Blob(["%PDF-1.7"]), {
          headers: { "Content-Type": "application/pdf" },
        });
      }),
    );
    renderExamples();

    await userEvent.click(await screen.findByRole("button", { name: "PDF" }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(requests).toEqual([{ path: "/api/examples/ex-doc/download/pdf", auth: null }]);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
