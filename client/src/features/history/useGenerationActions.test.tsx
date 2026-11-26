import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// The PNG re-export is stubbed so a test chooses how it fails.
const download = vi.hoisted(() => ({ error: null as unknown }));
vi.mock("@/features/generate/useCardExport", () => ({
  downloadCardPng: async () => {
    if (download.error) throw download.error;
  },
}));

import { CARD_EXPORT_FAILED_COPY, CardExportError } from "@/features/generate/cardExportError";
import { makeBrandProfile, makeGeneration } from "@/test/factories";
import { useGenerationActions } from "./useGenerationActions";

const CARD = makeGeneration({
  type: "card",
  output: {
    template_id: "quote",
    fields: { eyebrow: "", headline: "Hi", body: "", cta: "", hashtag: "" },
    image: null,
    accent_hex: null,
  } as never,
});

let latest: ReturnType<typeof useGenerationActions>;
let container: HTMLDivElement;
let root: Root;

function Harness() {
  latest = useGenerationActions(CARD, makeBrandProfile());
  return null;
}

function mount() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<Harness />));
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  download.error = null;
});

describe("useGenerationActions: PNG download errors read plainly", () => {
  it("maps a raw failure to the plain constant", async () => {
    download.error = new Error("Aborted(CompileError: WebAssembly.instantiate())");
    mount();
    await act(async () => latest.download());
    expect(latest.downloadError).toBe(CARD_EXPORT_FAILED_COPY);
  });

  it("keeps a curated message", async () => {
    download.error = new CardExportError("Could not load the workspace brand fonts.");
    mount();
    await act(async () => latest.download());
    expect(latest.downloadError).toBe("Could not load the workspace brand fonts.");
  });
});
