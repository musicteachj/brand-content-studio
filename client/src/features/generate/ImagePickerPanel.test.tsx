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
  uploadImage: vi.fn(() => Promise.resolve({ url: "/u", storage_key: "k1", source: "upload" })),
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

  it("offers Save to brand images after an upload and passes the file", async () => {
    const onSaveBrandImage = vi.fn(() => Promise.resolve());
    mount({ onSaveBrandImage });
    const file = new File(["x"], "shot.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [file] });
    await act(async () => {
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const save = document.querySelector('[aria-label="Save to brand images"]') as HTMLElement;
    expect(save).not.toBeNull();
    await act(async () => {
      save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(onSaveBrandImage).toHaveBeenCalledWith(file);
  });
});

describe("ImagePickerPanel Unsplash credit", () => {
  const PHOTO = {
    id: "abc123",
    description: "A green wall",
    thumb_url: "https://images.unsplash.com/small.jpg",
    preview_url: "https://images.unsplash.com/regular.jpg",
    width: 400,
    height: 500,
    color: "#1c3a2e",
    attribution: {
      author: "Jane Mason",
      author_url: "https://unsplash.com/@janemason?utm_source=Folio&utm_medium=referral",
      source_url: "https://unsplash.com/photos/abc123?utm_source=Folio&utm_medium=referral",
    },
    download_location: "https://api.unsplash.com/photos/abc123/download",
  };

  function mountWithResult(props: Partial<React.ComponentProps<typeof ImagePickerPanel>> = {}) {
    useUnsplashSearch.mockReturnValue({
      data: { query: "walls", page: 1, total_pages: 1, results: [PHOTO] },
      isLoading: false,
      isError: false,
    } as never);
    mount({ initialKeywords: ["walls"], brandImages: [], ...props });
  }

  afterEach(() => {
    useUnsplashSearch.mockReturnValue({ data: undefined, isLoading: false, isError: false });
  });

  function creditLinks(): HTMLAnchorElement[] {
    return Array.from(document.querySelectorAll("a"));
  }

  it("credits the photographer and Unsplash with links that open in a new tab", () => {
    mountWithResult();
    const credit = creditLinks()[0].closest("p");
    expect(credit?.textContent).toBe("Photo by Jane Mason on Unsplash");

    const [author, unsplash] = creditLinks();
    expect(author.textContent).toBe("Jane Mason");
    expect(author.getAttribute("href")).toBe(PHOTO.attribution.author_url);
    expect(unsplash.textContent).toBe("Unsplash");
    expect(unsplash.getAttribute("href")).toBe(
      "https://unsplash.com/?utm_source=Folio&utm_medium=referral",
    );
    for (const link of [author, unsplash]) {
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noreferrer");
    }
  });

  it("following a credit link does not select the photo", () => {
    const onSelectUnsplash = vi.fn();
    mountWithResult({ onSelectUnsplash });
    for (const link of creditLinks()) {
      // Keep jsdom from attempting navigation; the click still bubbles through React.
      link.addEventListener("click", (e) => e.preventDefault());
      act(() => link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })));
    }
    expect(onSelectUnsplash).not.toHaveBeenCalled();
  });
});
