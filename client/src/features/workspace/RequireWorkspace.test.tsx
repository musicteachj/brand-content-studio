import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const { useActiveWorkspaceMock } = vi.hoisted(() => ({ useActiveWorkspaceMock: vi.fn() }));
vi.mock("@/features/workspace/useActiveWorkspace", () => ({
  useActiveWorkspace: useActiveWorkspaceMock,
}));

import { RequireWorkspace } from "./RequireWorkspace";

let container: HTMLDivElement;
let root: Root;

function mountAt(path: string) {
  container = document.createElement("div");
  root = createRoot(container);
  act(() =>
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/assets"
            element={
              <RequireWorkspace>
                <div>ASSETS</div>
              </RequireWorkspace>
            }
          />
          <Route path="/setup" element={<div>SETUP</div>} />
        </Routes>
      </MemoryRouter>,
    ),
  );
}

beforeEach(() => {
  useActiveWorkspaceMock.mockReset();
});
afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
});

describe("RequireWorkspace", () => {
  it("redirects to /setup when the owner has no workspaces", () => {
    useActiveWorkspaceMock.mockReturnValue({ hasNone: true });
    mountAt("/assets");
    expect(container.textContent).toContain("SETUP");
  });

  it("renders children when a workspace exists", () => {
    useActiveWorkspaceMock.mockReturnValue({ hasNone: false });
    mountAt("/assets");
    expect(container.textContent).toContain("ASSETS");
  });

  it("does not redirect while loading or on error (hasNone is false)", () => {
    useActiveWorkspaceMock.mockReturnValue({ hasNone: false });
    mountAt("/assets");
    expect(container.textContent).toContain("ASSETS");
  });
});
