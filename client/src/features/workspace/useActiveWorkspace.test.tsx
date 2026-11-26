import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Workspace } from "@/types";
import { makeBrandProfile } from "@/test/factories";

// React act() so effects (the persist-on-resolve) flush synchronously.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Drive the resolver off a mocked workspaces query; the store stays real.
const { useWorkspacesMock } = vi.hoisted(() => ({ useWorkspacesMock: vi.fn() }));
vi.mock("@/api/workspaces", () => ({ useWorkspaces: useWorkspacesMock }));

import { useWorkspaceStore } from "@/stores/workspace";
import { useActiveWorkspace } from "./useActiveWorkspace";

function ws(id: string, name: string): Workspace {
  return {
    id,
    owner_id: "owner",
    name,
    slug: name.toLowerCase(),
    brand_profile: makeBrandProfile(),
    vector_namespace: id,
    embedding_model: "m",
    embedding_dim: 1536,
    asset_count: 0,
    ready_chunk_count: 0,
    created_at: null,
    updated_at: null,
  };
}

function mockList(data: Workspace[]) {
  useWorkspacesMock.mockReturnValue({ data, isLoading: false, isError: false });
}

let latest: ReturnType<typeof useActiveWorkspace>;
let container: HTMLDivElement;
let root: Root;

function Harness() {
  latest = useActiveWorkspace();
  return null;
}

function mount() {
  container = document.createElement("div");
  root = createRoot(container);
  act(() => root.render(<Harness />));
}

beforeEach(() => {
  useWorkspaceStore.setState({ activeId: null });
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  useWorkspacesMock.mockReset();
});

describe("useActiveWorkspace (Phase 4a)", () => {
  it("auto-selects the first workspace and persists it when none is chosen", () => {
    mockList([ws("a", "Alpha"), ws("b", "Beta")]);
    mount();
    expect(latest.workspace?.id).toBe("a");
    expect(useWorkspaceStore.getState().activeId).toBe("a");
  });

  it("honors a persisted active id (an explicit switch survives, no snap to first)", () => {
    useWorkspaceStore.setState({ activeId: "b" });
    mockList([ws("a", "Alpha"), ws("b", "Beta")]);
    mount();
    expect(latest.workspace?.id).toBe("b");
    expect(useWorkspaceStore.getState().activeId).toBe("b");
  });

  it("recovers from a stale id by falling back to the first workspace", () => {
    useWorkspaceStore.setState({ activeId: "gone" });
    mockList([ws("a", "Alpha")]);
    mount();
    expect(latest.workspace?.id).toBe("a");
    expect(useWorkspaceStore.getState().activeId).toBe("a");
  });

  it("reports hasNone for an empty workspace list", () => {
    mockList([]);
    mount();
    expect(latest.hasNone).toBe(true);
    expect(latest.workspace).toBeUndefined();
  });
});
