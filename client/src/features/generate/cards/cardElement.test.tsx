import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { afterEach, describe, expect, it } from "vitest";
import { buildCardElement, cleanGlyphs } from "./cardElement";
import type { BrandProfile, CardFields } from "@/types";

// Verdure-like workspace brand — serif/forest, NOT Folio's Jakarta/magenta.
const BRAND: BrandProfile = {
  colors: [
    { name: "Forest", hex: "#1C3A2E", role: "primary" },
    { name: "Cream", hex: "#F4F1E9", role: "neutral" },
    { name: "Ochre", hex: "#C98A3D", role: "accent" },
  ],
  accent_hex: "#1C3A2E",
  fonts: { heading: "DM Serif Display", body: "Spectral", mono: null },
  logo: null,
  voice_summary: null,
};

const FIELDS: CardFields = {
  eyebrow: "MATERIAL NOTES",
  headline: "Carbon, locked in the wall",
  body: "Hempcrete sequesters carbon for the building's whole life.",
  cta: "Read the field notes",
  hashtag: "#EmbodiedCarbon",
};

// App-chrome fonts that must NEVER leak into the card (DESIGN §7).
const FORBIDDEN_APP_FONTS = ["Plus Jakarta Sans", "DM Mono", "Inter"];

let container: HTMLDivElement | null = null;

function render(node: React.ReactElement): HTMLElement {
  container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  flushSync(() => root.render(node));
  return container;
}

afterEach(() => {
  container?.remove();
  container = null;
});

describe("card archetypes", () => {
  it("renders headline/body in the workspace fonts, never the app's", () => {
    const el = render(
      buildCardElement({
        template: "statement",
        fields: FIELDS,
        brand: BRAND,
        imageSrc: null,
        attribution: null,
      }),
    );

    const divs = [...el.querySelectorAll("div")];
    const headline = divs.find((d) => d.textContent === FIELDS.headline);
    expect(headline).toBeTruthy();
    // Computed font-family is the workspace heading font.
    expect(getComputedStyle(headline!).fontFamily).toContain("DM Serif Display");

    const body = divs.find((d) => d.textContent === FIELDS.body);
    expect(getComputedStyle(body!).fontFamily).toContain("Spectral");

    // No element in the card may use a Folio app font.
    for (const node of el.querySelectorAll<HTMLElement>("*")) {
      const family = node.style.fontFamily;
      for (const forbidden of FORBIDDEN_APP_FONTS) {
        expect(family).not.toContain(forbidden);
      }
    }
  });

  it("bakes the Unsplash attribution onto a photo-led card when present", () => {
    const el = render(
      buildCardElement({
        template: "photo-led",
        fields: FIELDS,
        brand: BRAND,
        imageSrc: "data:image/png;base64,AAAA",
        attribution: {
          author: "Jane Mason",
          author_url: "https://unsplash.com/@janemason",
          source_url: "https://unsplash.com/photos/abc",
        },
      }),
    );
    expect(el.textContent).toContain("Photo by Jane Mason on Unsplash");
  });

  it("strips glyphs the brand font can't render but keeps normal punctuation", () => {
    // Arrows / emoji / symbols → gone (they tofu in the latin font subset).
    expect(cleanGlyphs("See how we work upstream →")).toBe("See how we work upstream");
    expect(cleanGlyphs("Read more ➝ now ✨")).toBe("Read more now");
    // General punctuation (em dash, curly quotes, ellipsis) is preserved.
    expect(cleanGlyphs("change orders — can’t undo…")).toBe("change orders — can’t undo…");
  });

  it("the card never renders an arrow glyph in the CTA", () => {
    const el = render(
      buildCardElement({
        template: "photo-led",
        fields: { ...FIELDS, cta: "See how we work upstream →" },
        brand: BRAND,
        imageSrc: "data:image/png;base64,AAAA",
        attribution: null,
      }),
    );
    expect(el.textContent).toContain("See how we work upstream");
    expect(el.textContent).not.toContain("→");
  });

  it("omits attribution when there is no image", () => {
    const el = render(
      buildCardElement({
        template: "photo-led",
        fields: FIELDS,
        brand: BRAND,
        imageSrc: null,
        attribution: null,
      }),
    );
    expect(el.textContent).not.toContain("Photo by");
  });
});
