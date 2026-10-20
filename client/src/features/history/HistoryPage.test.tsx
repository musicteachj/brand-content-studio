import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { makeBrandProfile } from "@/test/factories";
import { useAuthStore } from "@/stores/auth";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";
import { HistoryPage } from "./HistoryPage";

vi.mock("@/features/workspace/useActiveWorkspace", () => ({
  useActiveWorkspace: () => ({
    workspace: { id: "ws1", brand_profile: makeBrandProfile() },
    workspaceId: "ws1",
  }),
}));

setupMswServer();

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("HistoryPage a11y", () => {
  // QA-10: the dialog had no Trigger, so closing it dropped focus to <body>.
  it("returns focus to the card that opened the detail dialog", async () => {
    renderPage();
    const card = await screen.findByRole("button", { name: /^text/i });
    card.focus();
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(card).toHaveFocus();
  });

  // QA-16: the selected filter wasn't exposed to assistive tech.
  it("marks the selected filter with aria-pressed", async () => {
    renderPage();
    const all = screen.getByRole("button", { name: "All" });
    const cards = screen.getByRole("button", { name: "Cards" });
    expect(all).toHaveAttribute("aria-pressed", "true");
    expect(cards).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(cards);
    expect(cards).toHaveAttribute("aria-pressed", "true");
    expect(all).toHaveAttribute("aria-pressed", "false");
  });

  // QA-04 (same class): deleting a generation was one click, and afterwards focus
  // went to the card being removed.
  it("confirms a generation delete, then focuses the page heading", async () => {
    useAuthStore.setState({
      token: "t",
      isAuthenticated: true,
      user: { id: "u1", email: "owner@example.com", full_name: "Owner", is_demo: false },
    });
    const deleted: string[] = [];
    server.use(
      http.delete("*/api/workspaces/ws1/generations/:id", ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /^text/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(
      await screen.findByRole("dialog", { name: "Delete this generation?" }),
    ).toBeInTheDocument();
    expect(deleted).toEqual([]);

    await userEvent.click(screen.getByRole("button", { name: "Delete generation" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deleted).toEqual(["gen-ws1"]);
    expect(screen.getByRole("heading", { level: 1, name: "Generations" })).toHaveFocus();
  });
});
