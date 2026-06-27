import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BrandImage } from "@/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Render the panel content inline (no portal / focus-scope) so we can target our
// own brand-image tiles without Radix's jsdom-unfriendly internals.
vi.mock("@radix-ui/react-dialog", () => {
  const Pass = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    Root: ({ children, open }: { children?: React.ReactNode; open: boolean }) =>
      open ? <div>{children}</div> : null,
    Portal: Pass,
    Overlay: Pass,
    Content: Pass,
    Title: Pass,
    Close: Pass,
  };
});

const { uploadImage, useUnsplashSearch, fetchImageDataUrl } = vi.hoisted(() => ({
  uploadImage: vi.fn(),
  useUnsplashSearch: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  fetchImageDataUrl: vi.fn(() => Promise.resolve("data:image/png;base64,AAAA")),
}));
vi.mock("@/api/images", () => ({ uploadImage, useUnsplashSearch, fetchImageDataUrl }));

import { ImagePickerPanel } from "./ImagePickerPanel";

const IMG: BrandImage = {
  id: "img1",
  storage_key: "ws/images/img1/logo.png",
  url: "/api/workspaces/ws/images/file/img1/logo.png",
  name: "logo.png",
};

let container: HTMLDivElement;
let root: Root;

function mount(props: Partial<React.ComponentProps<typeof ImagePickerPanel>> = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root.render(
      <ImagePickerPanel
        open
        onClose={() => {}}
        workspaceId="ws"
        initialKeywords={[]}
        selectedKey={null}
        brandImages={[IMG]}
        onSelectUnsplash={() => {}}
        onSelectUpload={() => {}}
        {...props}
      />,
    ),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
});

describe("ImagePickerPanel brand images", () => {
  it("renders a brand-images section with the workspace's saved images", () => {
    mount();
    expect(document.body.textContent).toContain("Brand images");
    expect(document.querySelector('[aria-label="Use logo.png"]')).not.toBeNull();
  });

  it("selecting a brand image calls onSelectUpload(url, storage_key)", () => {
    const onSelectUpload = vi.fn();
    mount({ onSelectUpload });
    const tile = document.querySelector('[aria-label="Use logo.png"]') as HTMLElement;
    act(() => tile.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onSelectUpload).toHaveBeenCalledWith(IMG.url, IMG.storage_key);
  });

  it("omits the brand-images section when there are none", () => {
    mount({ brandImages: [] });
    expect(document.body.textContent).not.toContain("Brand images");
  });
});
