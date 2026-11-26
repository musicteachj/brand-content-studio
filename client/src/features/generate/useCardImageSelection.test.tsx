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

const PERSISTED: CardImage = {
  source: "unsplash",
  url: "http://img/p.jpg",
  storage_key: null,
  unsplash_id: "abc",
  attribution: PHOTO.attribution,
};

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

  // QA-07: Remove used to be client-only, so the image came back on reload.
  it("clearImage un-picks the image and PATCHes image: null", async () => {
    mount("gen1");
    await act(async () => {
      await latest.selectUnsplash(PHOTO);
    });
    await act(async () => {});
    expect(patch).toHaveBeenCalledTimes(1);

    await act(async () => {
      latest.clearImage();
    });

    expect(latest.image).toBeNull();
    expect(latest.imageDataUrl).toBeNull();
    expect(patch).toHaveBeenCalledTimes(2);
    expect(patch.mock.calls[1]).toEqual(["/workspaces/ws1/generations/gen1", { image: null }]);
  });

  it("removing an image reopened from History clears it on the server", async () => {
    mount("gen1");
    await act(async () => {
      await latest.hydrate("gen1", PERSISTED);
    });
    await act(async () => {
      latest.clearImage();
    });

    expect(patch).toHaveBeenCalledTimes(1);
    expect(patch.mock.calls[0]).toEqual(["/workspaces/ws1/generations/gen1", { image: null }]);
  });

  it("clearImage before there's a generation doesn't PATCH", async () => {
    mount(null);
    await act(async () => {
      await latest.selectUnsplash(PHOTO);
    });
    await act(async () => {
      latest.clearImage();
    });

    expect(latest.image).toBeNull();
    expect(patch).not.toHaveBeenCalled();
  });

  it("the removal is sent only after a pending pick's PATCH settles", async () => {
    let resolvePick!: () => void;
    patch.mockImplementationOnce(() => new Promise((r) => (resolvePick = () => r({ data: {} }))));
    mount("gen1");
    await act(async () => {
      await latest.selectUnsplash(PHOTO);
    });
    await act(async () => {}); // pick PATCH is in flight
    await act(async () => {
      latest.clearImage();
    });
    expect(patch).toHaveBeenCalledTimes(1); // removal waits its turn

    await act(async () => {
      resolvePick();
    });
    expect(patch).toHaveBeenCalledTimes(2);
    expect(patch.mock.calls[1][1]).toEqual({ image: null });
  });

  it("the card clears only once the server has removed the image", async () => {
    let resolveRemove!: () => void;
    mount("gen1");
    await act(async () => {
      await latest.hydrate("gen1", PERSISTED);
    });
    patch.mockImplementationOnce(() => new Promise((r) => (resolveRemove = () => r({ data: {} }))));
    await act(async () => {
      latest.clearImage();
    });
    expect(latest.image?.unsplash_id).toBe("abc"); // still saved, still shown

    await act(async () => {
      resolveRemove();
    });
    expect(latest.image).toBeNull();
  });

  it("a failed removal keeps the image and says so", async () => {
    mount("gen1");
    await act(async () => {
      await latest.hydrate("gen1", PERSISTED);
    });
    patch.mockImplementationOnce(() => Promise.reject(new Error("offline")));
    await act(async () => {
      latest.clearImage();
    });

    expect(latest.image?.unsplash_id).toBe("abc");
    expect(latest.imageDataUrl).toBe("data:img");
    expect(latest.imageError).toMatch(/couldn.t remove the image/i);
  });

  it("a regenerate during a removal doesn't bring the image back", async () => {
    let resolveRemove!: () => void;
    mount("gen1");
    await act(async () => {
      await latest.hydrate("gen1", PERSISTED);
    });
    patch.mockImplementationOnce(() => new Promise((r) => (resolveRemove = () => r({ data: {} }))));
    await act(async () => {
      latest.clearImage();
    });
    expect(latest.removing).toBe(true);
    act(() => root.render(<Harness gid="gen2" />)); // regenerate delivers a new id
    await act(async () => {
      resolveRemove();
    });

    expect(latest.removing).toBe(false);
    expect(latest.image).toBeNull();
    expect(patch).toHaveBeenCalledTimes(1); // never attached to gen2
  });

  it("re-picking the same photo during a removal saves it after the removal", async () => {
    let resolveRemove!: () => void;
    mount("gen1");
    await act(async () => {
      await latest.hydrate("gen1", PERSISTED);
    });
    patch.mockImplementationOnce(() => new Promise((r) => (resolveRemove = () => r({ data: {} }))));
    await act(async () => {
      latest.clearImage();
    });
    await act(async () => {
      await latest.selectUnsplash(PHOTO); // same photo as the saved one
    });
    expect(patch).toHaveBeenCalledTimes(1); // waits for the removal
    await act(async () => {
      resolveRemove();
    });

    expect(latest.image?.unsplash_id).toBe("abc");
    expect(patch).toHaveBeenCalledTimes(2);
    expect((patch.mock.calls[1][1] as { image: CardImage }).image.unsplash_id).toBe("abc");
  });

  it("a second Remove while one is saving is ignored", async () => {
    let resolveRemove!: () => void;
    mount("gen1");
    await act(async () => {
      await latest.hydrate("gen1", PERSISTED);
    });
    patch.mockImplementationOnce(() => new Promise((r) => (resolveRemove = () => r({ data: {} }))));
    await act(async () => {
      latest.clearImage();
    });
    await act(async () => {
      latest.clearImage();
    });
    await act(async () => {
      resolveRemove();
    });

    expect(patch).toHaveBeenCalledTimes(1);
    expect(latest.image).toBeNull();
  });

  it("Remove with nothing picked sends nothing", async () => {
    mount("gen1");
    await act(async () => {
      latest.clearImage();
    });
    expect(patch).not.toHaveBeenCalled();
  });

  it("re-picking the same photo after Remove saves it again", async () => {
    mount("gen1");
    await act(async () => {
      await latest.selectUnsplash(PHOTO);
    });
    await act(async () => {});
    await act(async () => {
      latest.clearImage();
    });
    await act(async () => {
      await latest.selectUnsplash(PHOTO);
    });
    await act(async () => {});

    expect(patch).toHaveBeenCalledTimes(3);
    expect((patch.mock.calls[2][1] as { image: CardImage }).image.unsplash_id).toBe("abc");
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
