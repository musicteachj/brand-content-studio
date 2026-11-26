import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Enable React's act() so state updates flush synchronously in the harness.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Mock the axios instance so a save issues a PATCH and never a /generate call.
// `vi.hoisted` lets the mock fn exist before the hoisted vi.mock factory runs.
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { patch } }));

import { useCardEditor, type CardEditorBase } from "./useCardEditor";

const BASE: CardEditorBase = {
  generationId: "gen1",
  template: "photo-led",
  fields: {
    eyebrow: "EYEBROW",
    headline: "Original headline",
    body: "Body copy.",
    cta: "Read",
    hashtag: "#Tag",
  },
  accentHex: null,
};

type Editor = ReturnType<typeof useCardEditor>;
let latest: Editor;
let container: HTMLDivElement;

function Harness() {
  latest = useCardEditor("ws1", BASE);
  return null;
}

function mount() {
  container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(<Harness />));
}

beforeEach(() => {
  patch.mockResolvedValue({ data: {} });
});

afterEach(() => {
  container?.remove();
  patch.mockClear();
});

describe("useCardEditor (Phase 1.5)", () => {
  it("starts clean and tracks an inline edit as dirty", () => {
    mount();
    expect(latest.dirty).toBe(false);
    act(() => latest.setField("headline", "A sharper headline"));
    expect(latest.dirty).toBe(true);
    expect(latest.fields?.headline).toBe("A sharper headline");
  });

  it("saves via PATCH with only the changed keys — never a /generate call", async () => {
    mount();
    act(() => latest.setField("headline", "Edited"));
    act(() => latest.setTemplate("quote"));
    await act(async () => {
      await latest.save();
    });

    expect(patch).toHaveBeenCalledTimes(1);
    const [url, body] = patch.mock.calls[0];
    expect(url).toBe("/workspaces/ws1/generations/gen1");
    expect(url).not.toContain("generate");
    expect(body).toEqual({ fields: { ...BASE.fields, headline: "Edited" }, template_id: "quote" });
    // After a successful save the draft is the new baseline → clean again.
    expect(latest.dirty).toBe(false);
  });

  it("discard reverts to the last-saved baseline", () => {
    mount();
    act(() => latest.setField("headline", "Throwaway"));
    expect(latest.dirty).toBe(true);
    act(() => latest.discard());
    expect(latest.dirty).toBe(false);
    expect(latest.fields?.headline).toBe("Original headline");
  });

  it("only sends a palette accent when it actually changed", async () => {
    mount();
    act(() => latest.setAccent("#C98A3D"));
    await act(async () => {
      await latest.save();
    });
    expect(patch.mock.calls[0][1]).toEqual({ accent_hex: "#C98A3D" });
  });
});
