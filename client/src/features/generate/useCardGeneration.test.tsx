import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Capture the AbortSignal handed to the stream; never resolve (stay in-flight).
const { streamCard, captured } = vi.hoisted(() => ({
  streamCard: vi.fn(),
  captured: { signal: undefined as AbortSignal | undefined },
}));
vi.mock("@/lib/sse", () => ({
  streamCardGeneration: (_ws: string, _body: unknown, _h: unknown, signal?: AbortSignal) => {
    captured.signal = signal;
    streamCard();
    return new Promise(() => {});
  },
}));
vi.mock("@/api/images", () => ({ fetchImageDataUrl: vi.fn(), trackUnsplashDownload: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { patch: vi.fn() } }));

import { useCardGeneration } from "./useCardGeneration";

let latest: ReturnType<typeof useCardGeneration>;
let container: HTMLDivElement;
let root: Root;

function Harness({ ws }: { ws: string }) {
  latest = useCardGeneration(ws);
  return null;
}

beforeEach(() => {
  container = document.createElement("div");
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

describe("useCardGeneration abort-on-switch", () => {
  it("aborts the in-flight stream and resets when workspace changes", () => {
    act(() => root.render(<Harness ws="a" />));
    act(() => {
      void latest.generate({ brief: "x", template_id: "photo-led", tone: "default" });
    });
    expect(latest.status).toBe("streaming");
    const signal = captured.signal!;
    act(() => root.render(<Harness ws="b" />));
    expect(signal.aborted).toBe(true);
    expect(latest.status).toBe("idle");
  });
});
