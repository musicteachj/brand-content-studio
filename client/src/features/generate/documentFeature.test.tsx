import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the axios client so a download hits the auth-gated route and never /generate.
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { get } }));

import { DeckPreview } from "./DeckPreview";
import { DocumentPage } from "./DocumentPage";
import { downloadDocumentFile } from "./documentDownload";
import type { BrandProfile, DocumentModel } from "@/types";

// Verdure-like brand — serif/forest, NOT Folio's Jakarta/magenta.
const BRAND: BrandProfile = {
  colors: [
    { name: "Forest", hex: "#1C3A2E", role: "primary" },
    { name: "Cream", hex: "#F4F1E9", role: "neutral" },
    { name: "Ochre", hex: "#C98A3D", role: "accent" },
  ],
  accent_hex: null,
  fonts: { heading: "DM Serif Display", body: "Spectral", mono: null },
  logo: null,
  voice_summary: null,
};

const DOC: DocumentModel = {
  archetype: "one-pager",
  title: "Recycled-Denim Insulation",
  eyebrow: "Product brief",
  lede: "A high-performance insulation made from post-consumer denim.",
  sections: [
    { heading: "Why it matters", body: "It cuts embodied carbon.", bullets: ["Lower carbon"] },
  ],
  footer: "Verdure Materials",
};

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
  get.mockReset();
});

describe("DocumentPage", () => {
  it("renders the document in workspace fonts, never the app's", () => {
    const el = render(<DocumentPage document={DOC} brand={BRAND} />);

    // The page root carries the body font; section/lede text inherits it.
    const page = el.firstElementChild as HTMLElement;
    expect(page.style.fontFamily).toContain("Spectral");

    // Title + section headings take the heading font + primary brand color.
    const title = [...el.querySelectorAll("h2")].find((h) => h.textContent === DOC.title);
    expect(title).toBeTruthy();
    expect(title!.style.fontFamily).toContain("DM Serif Display");
    expect(getComputedStyle(title!).color).toBe("rgb(28, 58, 46)"); // #1C3A2E

    for (const node of el.querySelectorAll<HTMLElement>("*")) {
      for (const forbidden of FORBIDDEN_APP_FONTS) {
        expect(node.style.fontFamily).not.toContain(forbidden);
      }
    }
  });

  it("compact mode shows the header only (no sections)", () => {
    const el = render(<DocumentPage document={DOC} brand={BRAND} compact />);
    expect(el.textContent).toContain(DOC.title);
    expect(el.textContent).not.toContain("Why it matters");
  });
});

describe("DeckPreview", () => {
  const DECK: DocumentModel = { ...DOC, archetype: "short-deck" };

  it("renders a title slide + a slide per section, in workspace fonts", () => {
    const el = render(<DeckPreview document={DECK} brand={BRAND} />);
    expect(el.textContent).toContain(DECK.title);
    expect(el.textContent).toContain("Why it matters");

    const title = [...el.querySelectorAll("h2")].find((h) => h.textContent === DECK.title);
    expect(title!.style.fontFamily).toContain("DM Serif Display");
    expect(getComputedStyle(title!).color).toBe("rgb(28, 58, 46)"); // #1C3A2E

    for (const node of el.querySelectorAll<HTMLElement>("*")) {
      for (const forbidden of FORBIDDEN_APP_FONTS) {
        expect(node.style.fontFamily).not.toContain(forbidden);
      }
    }
  });

  it("compact mode shows the title slide only", () => {
    const el = render(<DeckPreview document={DECK} brand={BRAND} compact />);
    expect(el.textContent).toContain(DECK.title);
    expect(el.textContent).not.toContain("Why it matters");
  });
});

describe("downloadDocumentFile", () => {
  beforeEach(() => {
    get.mockResolvedValue({ data: new Blob(["x"]) });
    // jsdom doesn't implement object URLs or anchor navigation.
    globalThis.URL.createObjectURL = vi.fn(() => "blob:mock");
    globalThis.URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  it("pulls the file from the auth-gated download route — never /generate", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    await downloadDocumentFile("ws1", "gen1", "docx", "one-pager");

    expect(get).toHaveBeenCalledTimes(1);
    const [url, config] = get.mock.calls[0];
    expect(url).toBe("/workspaces/ws1/generations/gen1/download/docx");
    expect(url).not.toContain("generate");
    expect(config).toEqual({ responseType: "blob" });
    // The streaming path (fetch) is never touched by a re-download.
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
