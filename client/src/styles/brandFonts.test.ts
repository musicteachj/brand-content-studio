import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BrandFonts, UploadedFont } from "@/types";

const FONTS: BrandFonts = { heading: "Acme Sans", body: "Acme Sans", mono: null };

// The loader caches bytes and 404s in module state, so each test gets a fresh
// module: no result can depend on what an earlier test happened to fetch.
let mod: typeof import("./brandFonts");
beforeEach(async () => {
  vi.resetModules();
  mod = await import("./brandFonts");
});
afterEach(() => vi.unstubAllGlobals());

/** Stub fetch: CDN urls answer per `cdn`, everything else (uploaded and bundled
 *  same-origin assets) answers 200 with one marker byte. */
function stubFetch(
  cdn: (url: string) => "ok" | "404" | "throw",
  sameOrigin: "ok" | "throw" = "ok",
) {
  const body = (b: number) => ({
    ok: true,
    status: 200,
    arrayBuffer: async () => new Uint8Array([b]).buffer,
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const outcome = url.includes("cdn.jsdelivr.net") ? cdn(url) : sameOrigin;
      if (outcome === "throw") throw new TypeError("network down");
      if (outcome === "404")
        return { ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) };
      return body(url.includes("cdn.jsdelivr.net") ? 2 : 1);
    }),
  );
  return fetch as unknown as ReturnType<typeof vi.fn>;
}

// The glyph fallbacks always ride along (QA-17); most tests are about the brand faces.
const brandOnly = <T extends { name: string }>(fonts: T[]) =>
  fonts.filter((f) => f.name !== mod.SCRIPTS_FAMILY && f.name !== mod.SYMBOLS_FAMILY);

describe("loadBrandFontBuffers source-awareness", () => {
  it("fetches uploaded fonts from their own (same-origin) url", async () => {
    const f = stubFetch(() => "ok");
    const uploaded: UploadedFont[] = [
      {
        id: "f1",
        family: "Acme Sans",
        storage_key: "k",
        url: "/api/workspaces/w/fonts/file/f1/a.ttf",
      },
    ];
    const out = await mod.loadBrandFontBuffers(FONTS, uploaded);
    expect(brandOnly(out).length).toBeGreaterThan(0);
    expect(brandOnly(out).every((x) => x.name === "Acme Sans")).toBe(true);
    expect(f.mock.calls.some(([u]) => String(u).includes("/fonts/file/"))).toBe(true);
  });

  it("falls back to the CDN when the family isn't uploaded", async () => {
    const f = stubFetch(() => "ok");
    await mod.loadBrandFontBuffers(FONTS, []);
    expect(f.mock.calls.some(([u]) => String(u).includes("cdn.jsdelivr.net"))).toBe(true);
  });

  it("defaults an unset brand to the bundled fallback, without asking the CDN", async () => {
    const f = stubFetch(() => "ok");
    const unset = { heading: null, body: null, mono: null };
    const out = await mod.loadBrandFontBuffers(unset, []);
    const urls = f.mock.calls.map(([u]) => String(u));
    expect(mod.headingFamily(unset)).toBe(mod.FALLBACK_FAMILY);
    expect(urls.some((u) => u.includes("cdn.jsdelivr.net"))).toBe(false);
    expect(urls.some((u) => u.includes("lora-latin-400-normal"))).toBe(true);
    expect(brandOnly(out).length).toBeGreaterThan(0);
    expect(brandOnly(out).every((x) => x.name === mod.FALLBACK_FAMILY)).toBe(true);
  });
});

// QA-06 / QA-14: a family the CDN doesn't have (a system font, a typo, a style
// description) used to leave Satori with no fonts, so Export PNG never enabled.
describe("loadBrandFontBuffers fallback", () => {
  it("stands in the bundled font, under the requested name, for every weight", async () => {
    stubFetch(() => "404");
    const fonts: BrandFonts = { heading: "Clean sans-serif", body: "Clean sans-serif", mono: null };
    const out = brandOnly(await mod.loadBrandFontBuffers(fonts, []));
    expect(out.map((x) => x.weight).sort()).toEqual([400, 600, 700]);
    expect(out.every((x) => x.name === "Clean sans-serif")).toBe(true);
    // CDN bytes are marked 2, bundled bytes 1: every face is the bundled fallback.
    expect(out.every((x) => new Uint8Array(x.data)[0] === 1)).toBe(true);
  });

  it("keeps a single-weight family's own face instead of mixing in the fallback", async () => {
    // DM Serif Display ships 400 only: the 700 request 404s, the family is real.
    stubFetch((url) => (url.includes("-400-") ? "ok" : "404"));
    const fonts: BrandFonts = { heading: "DM Serif Display", body: "DM Serif Display", mono: null };
    const out = brandOnly(await mod.loadBrandFontBuffers(fonts, []));
    expect(out.map((x) => x.weight)).toEqual([400]);
    expect(out[0].name).toBe("DM Serif Display");
    expect(new Uint8Array(out[0].data)[0]).toBe(2);
  });

  it("doesn't swap in the fallback on a transient failure", async () => {
    // Offline / CDN 5xx: the brand font may well exist, so return nothing (the
    // export then shows its retryable error) instead of exporting Lora.
    stubFetch(() => "throw");
    const fonts: BrandFonts = { heading: "Work Sans", body: "Work Sans", mono: null };
    expect(await mod.loadBrandFontBuffers(fonts, [])).toEqual([]);
  });
});

// QA-17: the card fonts' Latin subsets lack ₂, ≥, → and friends, so they exported
// as NO GLYPH boxes. Bundled glyph faces ride at the end of the list, where Satori
// only reaches for them when the brand face lacks a character.
describe("loadBrandFontBuffers glyph fallbacks", () => {
  it("appends the scripts (400, 700) and symbols (400) faces last", async () => {
    stubFetch(() => "ok");
    const out = await mod.loadBrandFontBuffers(
      { heading: "Fraunces", body: "Inter", mono: null },
      [],
    );
    expect(out[0].name).toBe("Fraunces");
    expect(out.slice(-3).map((x) => `${x.name}:${x.weight}`)).toEqual([
      `${mod.SCRIPTS_FAMILY}:400`,
      `${mod.SCRIPTS_FAMILY}:700`,
      `${mod.SYMBOLS_FAMILY}:400`,
    ]);
  });

  it("reports a retryable failure rather than exporting without them", async () => {
    // Brand fonts load from the CDN, but the same-origin glyph assets don't.
    stubFetch(() => "ok", "throw");
    expect(
      await mod.loadBrandFontBuffers({ heading: "Fraunces", body: "Inter", mono: null }, []),
    ).toEqual([]);
  });
});
