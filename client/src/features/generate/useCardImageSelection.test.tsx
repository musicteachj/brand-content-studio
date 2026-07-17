import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { patch } }));
const { fetchImageDataUrl, trackUnsplashDownload } = vi.hoisted(() => ({
  fetchImageDataUrl: vi.fn(),
  trackUnsplashDownload: vi.fn(),
}));
vi.mock("@/api/images", () => ({ fetchImageDataUrl, trackUnsplashDownload }));

import { useCardImageSelection } from "./useCardImageSelection";
import type { CardImage, UnsplashPhoto } from "@/types";

const PHOTO = {
  id: "abc",
  preview_url: "http://img/p.jpg",
  download_location: "http://img/d",
  attribution: { author: "Jo", author_url: "http://x", source_url: "http://y" },
} as unknown as UnsplashPhoto;

type Hook = ReturnType<typeof useCardImageSelection>;
let latest: Hook;
let container: HTMLDivElement;
let root: Root;

function Harness({ gid }: { gid: string | null }) {
  latest = useCardImageSelection("ws1", gid);
  return null;
}
function mount(gid: string | null) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<Harness gid={gid} />));
}

beforeEach(() => {
  patch.mockResolvedValue({ data: {} });
  fetchImageDataUrl.mockResolvedValue("data:img");
  trackUnsplashDownload.mockResolvedValue(undefined);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

describe("useCardImageSelection", () => {
  it("PATCHes the picked image onto the generation exactly once", async () => {
    mount("gen1");
    await act(async () => {
      await latest.selectUnsplash(PHOTO);
    });
    await act(async () => {}); // flush the persist effect

    expect(latest.image?.unsplash_id).toBe("abc");
    expect(latest.imageDataUrl).toBe("data:img");
    expect(patch).toHaveBeenCalledTimes(1);
    const [url, body] = patch.mock.calls[0];
    expect(url).toBe("/workspaces/ws1/generations/gen1");
    expect((body as { image: CardImage }).image.unsplash_id).toBe("abc");
  });

  it("clearImage un-picks the image and does not PATCH (the ARCH-04 bug fix)", async () => {
    mount("gen1");
    await act(async () => {
      await latest.selectUnsplash(PHOTO);
    });
    await act(async () => {});
    expect(patch).toHaveBeenCalledTimes(1);

    act(() => {
      latest.clearImage();
    });
    await act(async () => {});

    expect(latest.image).toBeNull();
    expect(latest.imageDataUrl).toBeNull();
    expect(patch).toHaveBeenCalledTimes(1); // clearing does not PATCH
  });

  it("clearImage cancels an in-flight pick — the resolving fetch can't resurrect it", async () => {
    let resolveFetch!: (v: string) => void;
    fetchImageDataUrl.mockImplementationOnce(() => new Promise((r) => (resolveFetch = r)));
    mount("gen1");

    let pick!: Promise<void>;
    act(() => {
      pick = latest.selectUnsplash(PHOTO); // fetch is pending
    });
    act(() => {
      latest.clearImage(); // Remove clicked before the fetch resolves
    });
    await act(async () => {
      resolveFetch("data:img"); // the stale fetch resolves
      await pick;
    });

    expect(latest.image).toBeNull(); // stays cleared — not resurrected
    expect(latest.imageDataUrl).toBeNull();
  });

  it("hydrate seeds a persisted image without re-PATCHing it", async () => {
    mount("gen1");
    const persisted: CardImage = {
      source: "unsplash",
      url: "http://img/p.jpg",
      storage_key: null,
      unsplash_id: "abc",
      attribution: PHOTO.attribution,
    };
    await act(async () => {
      await latest.hydrate("gen1", persisted);
    });
    await act(async () => {});

    expect(latest.image?.unsplash_id).toBe("abc");
    expect(latest.imageDataUrl).toBe("data:img");
    expect(patch).not.toHaveBeenCalled();
  });
});
