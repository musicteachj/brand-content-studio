import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// SEC-11: the font family is a user-controlled label. The old code interpolated
// it into a <style>@font-face string, so a crafted name could inject arbitrary
// CSS. The fix routes through the CSSOM FontFace API, which takes the family as a
// discrete argument and quotes it — no string concatenation into CSS.

interface Captured {
  family: string;
  source: string | ArrayBuffer;
  unicodeRange?: string;
}

// injectFontFace dedupes per family in module state, so each test gets a fresh
// module (and fresh caches).
let injectFontFace: typeof import("./brandFonts").injectFontFace;
beforeEach(async () => {
  vi.resetModules();
  ({ injectFontFace } = await import("./brandFonts"));
});

/** A FontFace stand-in that records every face and fails `load()` per `fails`. */
function stubFontFace(calls: Captured[], fails: (c: Captured) => boolean) {
  class FakeFontFace {
    private readonly captured: Captured;
    constructor(family: string, source: string | ArrayBuffer, desc?: { unicodeRange?: string }) {
      this.captured = { family, source, unicodeRange: desc?.unicodeRange };
      calls.push(this.captured);
    }
    load() {
      return fails(this.captured)
        ? Promise.reject(new Error("load failed"))
        : Promise.resolve(this);
    }
  }
  vi.stubGlobal("FontFace", FakeFontFace);
}

const brandFaces = (calls: Captured[]) => calls.filter((c) => !c.unicodeRange);
const glyphFaces = (calls: Captured[]) => calls.filter((c) => c.unicodeRange);

describe("brand font injection uses the CSSOM FontFace API (SEC-11)", () => {
  let added: unknown[];
  beforeEach(() => {
    added = [];
    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: { add: (f: unknown) => added.push(f), delete: vi.fn() },
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(document, "fonts");
    document.head.querySelectorAll("style").forEach((s) => s.remove());
  });

  it("passes the family to FontFace as data, never concatenated into CSS", () => {
    const calls: Captured[] = [];
    stubFontFace(calls, () => false);
    const evil = 'X";}body{background:url(//evil)}@font-face{font-family:"Y';
    injectFontFace(evil);

    // The payload reaches FontFace as the family argument (data), so the browser
    // quotes it. It is never assembled into a CSS declaration.
    expect(brandFaces(calls)).toHaveLength(1);
    expect(calls.every((c) => c.family === evil)).toBe(true);
    expect(added).toHaveLength(calls.length);

    // And the old sink is gone: no <style> element carries the injected CSS.
    const leaked = Array.from(document.head.querySelectorAll("style")).some((s) =>
      (s.textContent ?? "").includes("body{background"),
    );
    expect(leaked).toBe(false);
  });

  it("registers the glyph fallbacks under the brand's name, ranged, before the brand face", () => {
    // QA-17: preview == export for characters the brand face lacks (₂, ≥, →).
    const calls: Captured[] = [];
    stubFontFace(calls, () => false);
    injectFontFace("Fraunces");

    const glyphs = glyphFaces(calls);
    expect(glyphs.map((c) => c.unicodeRange)).toEqual([
      expect.stringContaining("U+2070-209F"),
      expect.stringContaining("U+2264-2265"),
    ]);
    expect(glyphs.every((c) => c.family === "Fraunces")).toBe(true);
    // The brand face comes last, so the browser tries it first for any character.
    expect(calls[calls.length - 1].unicodeRange).toBeUndefined();
  });

  it("registers the bundled fallback bytes when a CDN face fails to load", async () => {
    const calls: Captured[] = [];
    stubFontFace(
      calls,
      (c) => typeof c.source === "string" && c.source.includes("cdn.jsdelivr.net"),
    );
    // The family isn't on the CDN at any weight; the bundled asset is.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("cdn.jsdelivr.net")
          ? { ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) }
          : { ok: true, arrayBuffer: async () => new Uint8Array([7]).buffer },
      ),
    );

    injectFontFace("Nowhere Grotesk");
    await vi.waitFor(() => expect(brandFaces(calls)).toHaveLength(2));
    const fallback = brandFaces(calls)[1];
    expect(fallback.family).toBe("Nowhere Grotesk");
    expect(fallback.source).toBeInstanceOf(ArrayBuffer);
  });

  it("retries a CDN face after a transient failure instead of falling back", async () => {
    const calls: Captured[] = [];
    stubFontFace(calls, () => true);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );

    injectFontFace("Blip Sans");
    await vi.waitFor(() =>
      expect((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1),
    );
    await new Promise((r) => setTimeout(r, 0));
    expect(brandFaces(calls).every((c) => typeof c.source === "string")).toBe(true);
    injectFontFace("Blip Sans");
    expect(brandFaces(calls)).toHaveLength(2);
  });
});
