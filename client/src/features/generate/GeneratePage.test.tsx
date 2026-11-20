import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { appStatusQuery, type AppStatus } from "@/api/status";
import { GeneratePage } from "./GeneratePage";

vi.mock("@/features/workspace/useActiveWorkspace", () => ({
  useActiveWorkspace: () => ({ workspace: { ready_chunk_count: 3 }, workspaceId: "ws1" }),
}));
vi.mock("@/features/generate/modes/TextMode", () => ({ TextMode: () => <p>brief</p> }));

function renderPage(available: boolean) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData<AppStatus>(appStatusQuery.queryKey, {
    live_ai_available: available,
    live_ai_reason: available ? "available" : "paused",
    turnstile_site_key: "k",
    password_login: false,
  });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <GeneratePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GeneratePage", () => {
  it("says live generation is paused and links to the examples", () => {
    renderPage(false);
    expect(screen.getByRole("status")).toHaveTextContent("Live generation is paused right now.");
    expect(screen.getByRole("link", { name: "Browse the ready-made examples" })).toHaveAttribute(
      "href",
      "/examples",
    );
  });

  it("shows no notice while live AI is available", () => {
    renderPage(true);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
