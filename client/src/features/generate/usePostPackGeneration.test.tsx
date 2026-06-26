import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Mock the axios client + image helpers so a generation is never hit and an image
// selection is a PATCH (never a /generate call).
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { patch } }));
const { fetchImageDataUrl, trackUnsplashDownload } = vi.hoisted(() => ({
  fetchImageDataUrl: vi.fn(),
  trackUnsplashDownload: vi.fn(),
}));
vi.mock("@/api/images", () => ({ fetchImageDataUrl, trackUnsplashDownload }));

import { usePostPackGeneration } from "./usePostPackGeneration";
import type { Generation, UnsplashPhoto } from "@/types";

const GEN = {
  id: "gen1",
  type: "post_pack",
  output: {
    post_text: "Specify hempcrete early.",
    hashtags: ["#Hempcrete"],
    char_count: 24,
    card: {
      template_id: "photo-led",
      fields: {
        eyebrow: "MATERIALS",
        headline: "Carbon, in the wall",
        body: "",
        cta: "Read",
        hashtag: "#Hempcrete",
      },
      image: null,
      suggested_keywords: ["hemp"],
      accent_hex: null,
    },
  },
} as unknown as Generation;

const PHOTO = {
  id: "abc",
  preview_url: "http://img/p.jpg",
  download_location: "http://img/d",
  attribution: { author: "Jo", author_url: "http://x", source_url: "http://y" },
} as unknown as UnsplashPhoto;

type Hook = ReturnType<typeof usePostPackGeneration>;
let latest: Hook;
let container: HTMLDivElement;

function Harness() {
  latest = usePostPackGeneration("ws1");
  return null;
}
function mount() {
  container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(<Harness />));
}

beforeEach(() => {
  patch.mockResolvedValue({ data: {} });
  fetchImageDataUrl.mockResolvedValue("data:img");
  trackUnsplashDownload.mockResolvedValue(undefined);
});
afterEach(() => {
  container?.remove();
  patch.mockReset();
  fetchImageDataUrl.mockReset();
  trackUnsplashDownload.mockReset();
});

describe("usePostPackGeneration", () => {
  it("hydrates a re-opened post_pack (caption + nested card) with no model call", async () => {
    mount();
    await act(async () => {
      await latest.loadGeneration(GEN);
    });
    expect(latest.status).toBe("done");
    expect(latest.caption).toBe("Specify hempcrete early.");
    expect(latest.fields?.headline).toBe("Carbon, in the wall");
    expect(latest.templateId).toBe("photo-led");
    expect(latest.suggestedKeywords).toEqual(["hemp"]);
    expect(patch).not.toHaveBeenCalled(); // image already attached → no re-PATCH
  });

  it("selecting an image PATCHes the generation — never a /generate call", async () => {
    mount();
    await act(async () => {
      await latest.loadGeneration({
        ...GEN,
        output: {
          ...(GEN.output as object),
          card: { ...(GEN.output as { card: object }).card, suggested_keywords: ["hemp"] },
        },
      } as unknown as Generation);
    });
    await act(async () => {
      await latest.selectUnsplash(PHOTO);
    });
    await act(async () => {}); // flush the persist effect

    expect(patch).toHaveBeenCalledTimes(1);
    const [url, body] = patch.mock.calls[0];
    expect(url).toBe("/workspaces/ws1/generations/gen1");
    expect(url).not.toContain("generate");
    expect((body as { image: { unsplash_id: string } }).image.unsplash_id).toBe("abc");
  });
});
