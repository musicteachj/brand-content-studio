import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const { useActiveWorkspaceMock, useGenerationCountMock } = vi.hoisted(() => ({
  useActiveWorkspaceMock: vi.fn(),
  useGenerationCountMock: vi.fn(),
}));
vi.mock("@/features/workspace/useActiveWorkspace", () => ({
  useActiveWorkspace: useActiveWorkspaceMock,
}));
vi.mock("@/api/generations", () => ({ useGenerationCount: useGenerationCountMock }));
vi.mock("@/stores/auth", () => ({
  useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { full_name: "Jane Doe" } }),
}));

import { DashboardPage } from "./DashboardPage";

let container: HTMLDivElement;
let root: Root;

function mount() {
  container = document.createElement("div");
  root = createRoot(container);
  act(() =>
    root.render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    ),
  );
}

beforeEach(() => {
  useGenerationCountMock.mockReturnValue({ data: 0 });
});
afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  vi.clearAllMocks();
});

describe("DashboardPage first-run", () => {
  it("shows the create-workspace CTA when the owner has no workspaces", () => {
    useActiveWorkspaceMock.mockReturnValue({
      workspace: undefined,
      workspaceId: null,
      isError: false,
      hasNone: true,
    });
    mount();
    expect(container.textContent).toContain("Create your first workspace");
    expect(container.textContent).not.toContain("Brand assets");
  });

  it("shows the stat grid when a workspace exists", () => {
    useActiveWorkspaceMock.mockReturnValue({
      workspace: { asset_count: 2, ready_chunk_count: 5 },
      workspaceId: "a",
      isError: false,
      hasNone: false,
    });
    mount();
    expect(container.textContent).toContain("Brand assets");
    expect(container.textContent).not.toContain("Create your first workspace");
  });

  // QA-01: the Phase 0 "scaffold is live" line and a stat hint that undercounted.
  it("uses current copy for the subtitle and the Generations stat", () => {
    useActiveWorkspaceMock.mockReturnValue({
      workspace: { asset_count: 2, ready_chunk_count: 5 },
      workspaceId: "a",
      isError: false,
      hasNone: false,
    });
    mount();
    expect(container.textContent).not.toMatch(/scaffold/i);
    expect(container.textContent).toContain("LinkedIn posts, cards, and documents");
    expect(container.textContent).toContain("Posts, cards, and documents");
  });
});
