import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadBrandFontBuffers } from "./brandFonts";
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
      { id: "f1", family: "Acme Sans", storage_key: "k", url: "/api/workspaces/w/fonts/file/f1/a.ttf" },
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
});
