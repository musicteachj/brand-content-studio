import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildCardElement, cardColors } from "./cardElement";
import type { CardFields } from "@/types";
import { makeBrandProfile } from "@/test/factories";

const BRAND = makeBrandProfile({
  colors: [
    { name: "Forest", hex: "#1C3A2E", role: "primary" },
    { name: "Cream", hex: "#F4F1E9", role: "neutral" },
    { name: "Ochre", hex: "#C98A3D", role: "accent" },
  ],
  accent_hex: "#1C3A2E",
  fonts: { heading: "DM Serif Display", body: "Spectral", mono: null },
});

const FIELDS: CardFields = {
  eyebrow: "MATERIAL NOTES",
  headline: "Carbon, locked in the wall",
  body: "Hempcrete sequesters carbon.",
  cta: "Read the notes",
  hashtag: "#EmbodiedCarbon",
};

let container: HTMLDivElement | null = null;
function render(node: React.ReactElement): HTMLElement {
  const el = document.createElement("div");
  container = el;
  document.body.appendChild(el);
  const root = createRoot(el);
  flushSync(() => root.render(node));
  return el;
}
afterEach(() => {
  container?.remove();
  container = null;
});

describe("per-card accent (Phase 1.5)", () => {
  it("uses the role-based accent when no override is given", () => {
    // accent_hex equals the primary ink, so cardColors falls back to the accent role.
    expect(cardColors(BRAND).accent).toBe("#C98A3D");
  });

  it("lets a per-card override win over the brand default", () => {
    expect(cardColors(BRAND, "#F4F1E9").accent).toBe("#F4F1E9");
  });

  it("ignores an override equal to the ink (would be invisible)", () => {
    expect(cardColors(BRAND, "#1C3A2E").accent).toBe("#C98A3D");
  });
});

describe("inline editing (Phase 1.5)", () => {
  it("renders contentEditable fields only when an edit handler is provided", () => {
    const locked = render(
      buildCardElement({
        template: "statement",
        fields: FIELDS,
        brand: BRAND,
        imageSrc: null,
        attribution: null,
      }),
    );
    expect(locked.querySelectorAll('[contenteditable="true"]').length).toBe(0);

    const onEdit = vi.fn();
    const editing = render(
      buildCardElement({
        template: "statement",
        fields: FIELDS,
        brand: BRAND,
        imageSrc: null,
        attribution: null,
        edit: { onEdit },
      }),
    );
    const editables = editing.querySelectorAll('[contenteditable="true"]');
    // eyebrow, headline, body, cta, hashtag.
    expect(editables.length).toBe(5);
  });

  it("emits edits via onEdit with the field key", () => {
    const onEdit = vi.fn();
    const el = render(
      buildCardElement({
        template: "statement",
        fields: FIELDS,
        brand: BRAND,
        imageSrc: null,
        attribution: null,
        edit: { onEdit },
      }),
    );
    const headline = [...el.querySelectorAll<HTMLElement>('[contenteditable="true"]')].find(
      (n) => n.getAttribute("aria-label") === "Headline",
    );
    expect(headline).toBeTruthy();
    headline!.textContent = "A new headline";
    headline!.dispatchEvent(new Event("input", { bubbles: true }));
    expect(onEdit).toHaveBeenCalledWith("headline", "A new headline");
  });
});
