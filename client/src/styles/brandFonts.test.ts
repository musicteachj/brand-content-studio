import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FALLBACK_FAMILY, headingFamily, loadBrandFontBuffers } from "./brandFonts";
import type { BrandFonts, UploadedFont } from "@/types";

const FONTS: BrandFonts = { heading: "Acme Sans", body: "Acme Sans", mono: null };

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      arrayBuffer: async () => new Uint8Array([url.startsWith("/") ? 1 : 2]).buffer,
    })),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("loadBrandFontBuffers source-awareness", () => {
  it("fetches uploaded fonts from their own (same-origin) url", async () => {
    const uploaded: UploadedFont[] = [
      {
        id: "f1",
        family: "Acme Sans",
        storage_key: "k",
        url: "/api/workspaces/w/fonts/file/f1/a.ttf",
      },
    ];
    const out = await loadBrandFontBuffers(FONTS, uploaded);
    expect(out.length).toBeGreaterThan(0);
    expect(out.every((f) => f.name === "Acme Sans")).toBe(true);
    const calledOwnUrl = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some(
      ([u]) => typeof u === "string" && u.includes("/fonts/file/"),
    );
    expect(calledOwnUrl).toBe(true);
  });

  it("falls back to the CDN when the family isn't uploaded", async () => {
    await loadBrandFontBuffers(FONTS, []);
    const calledCdn = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some(
      ([u]) => typeof u === "string" && u.includes("cdn.jsdelivr.net"),
    );
    expect(calledCdn).toBe(true);
  });

  it("defaults an unset brand to the bundled fallback, without asking the CDN", async () => {
    const out = await loadBrandFontBuffers({ heading: null, body: null, mono: null }, []);
    const urls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(([u]) => String(u));
    expect(headingFamily({ heading: null, body: null, mono: null })).toBe(FALLBACK_FAMILY);
    expect(urls.some((u) => u.includes("cdn.jsdelivr.net"))).toBe(false);
    expect(urls.some((u) => u.includes("lora-latin-400-normal"))).toBe(true);
    expect(out.length).toBeGreaterThan(0);
    expect(out.every((f) => f.name === FALLBACK_FAMILY)).toBe(true);
  });
});

// QA-06 / QA-14: a family the CDN doesn't have (a system font, a typo, a style
// description) used to leave Satori with no fonts, so Export PNG never enabled.
describe("loadBrandFontBuffers fallback", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("cdn.jsdelivr.net")
          ? { ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) }
          : { ok: true, arrayBuffer: async () => new Uint8Array([9]).buffer },
      ),
    );
  });

  it("stands in the bundled font, under the requested name, for every weight", async () => {
    const fonts: BrandFonts = { heading: "Clean sans-serif", body: "Clean sans-serif", mono: null };
    const out = await loadBrandFontBuffers(fonts, []);
    expect(out.map((f) => f.weight).sort()).toEqual([400, 600, 700]);
    expect(out.every((f) => f.name === "Clean sans-serif")).toBe(true);
    // The CDN 404s every request here, so any bytes are the bundled fallback.
    expect(out.every((f) => f.data.byteLength > 0)).toBe(true);
  });

  it("keeps a single-weight family's own face instead of mixing in the fallback", async () => {
    // DM Serif Display ships 400 only: the 700 request 404s, the family is real.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("cdn.jsdelivr.net") && !url.includes("-400-")
          ? { ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) }
          : { ok: true, arrayBuffer: async () => new Uint8Array([5]).buffer },
      ),
    );
    const fonts: BrandFonts = { heading: "DM Serif Display", body: "DM Serif Display", mono: null };
    const out = await loadBrandFontBuffers(fonts, []);
    expect(out.map((f) => f.weight)).toEqual([400]);
    expect(out[0].name).toBe("DM Serif Display");
  });

  it("doesn't swap in the fallback on a transient failure", async () => {
    // Offline / CDN 5xx: the brand font may well exist, so leave the list short
    // (the export then shows its retryable error) instead of exporting Lora.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("cdn.jsdelivr.net")) throw new TypeError("network down");
        return { ok: true, status: 200, arrayBuffer: async () => new Uint8Array([3]).buffer };
      }),
    );
    const fonts: BrandFonts = { heading: "Work Sans", body: "Work Sans", mono: null };
    expect(await loadBrandFontBuffers(fonts, [])).toEqual([]);
  });
});
