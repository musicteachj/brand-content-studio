import { afterEach, describe, expect, it, vi } from "vitest";
import { injectFontFace } from "./brandFonts";

// SEC-11: the font family is a user-controlled label. The old code interpolated
// it into a <style>@font-face string, so a crafted name could inject arbitrary
// CSS. The fix routes through the CSSOM FontFace API, which takes the family as a
// discrete argument and quotes it — no string concatenation into CSS.

interface Captured {
  family: string;
  source: string | ArrayBuffer;
}

describe("brand font injection uses the CSSOM FontFace API (SEC-11)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(document, "fonts");
    document.head.querySelectorAll("style").forEach((s) => s.remove());
  });

  it("passes the family to FontFace as data, never concatenated into CSS", () => {
    const calls: Captured[] = [];
    class FakeFontFace {
      constructor(
        public family: string,
        public source: string | ArrayBuffer,
      ) {
        calls.push({ family, source });
      }
      load() {
        return Promise.resolve(this);
      }
    }
    vi.stubGlobal("FontFace", FakeFontFace);
    const added: unknown[] = [];
    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: { add: (f: unknown) => added.push(f), delete: vi.fn() },
    });

    const evil = 'X";}body{background:url(//evil)}@font-face{font-family:"Y';
    injectFontFace(evil);

    // The payload reaches FontFace as the family argument (data), so the browser
    // quotes it. It is never assembled into a CSS declaration.
    expect(calls).toHaveLength(1);
    expect(calls[0].family).toBe(evil);
    expect(added).toHaveLength(1);

    // And the old sink is gone: no <style> element carries the injected CSS.
    const leaked = Array.from(document.head.querySelectorAll("style")).some((s) =>
      (s.textContent ?? "").includes("body{background"),
    );
    expect(leaked).toBe(false);
  });

  it("registers the bundled fallback bytes when a CDN face fails to load", async () => {
    const calls: Captured[] = [];
    class FailingCdnFace {
      constructor(
        public family: string,
        public source: string | ArrayBuffer,
      ) {
        calls.push({ family, source });
      }
      load() {
        return typeof this.source === "string" && this.source.includes("cdn.jsdelivr.net")
          ? Promise.reject(new Error("404"))
          : Promise.resolve(this);
      }
    }
    vi.stubGlobal("FontFace", FailingCdnFace);
    // The family isn't on the CDN at any weight; the bundled asset is.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("cdn.jsdelivr.net")
          ? { ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) }
          : { ok: true, arrayBuffer: async () => new Uint8Array([7]).buffer },
      ),
    );
    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: { add: vi.fn(), delete: vi.fn() },
    });

    injectFontFace("Nowhere Grotesk");
    await vi.waitFor(() => expect(calls.length).toBe(2));
    expect(calls[1].family).toBe("Nowhere Grotesk");
    expect(calls[1].source).toBeInstanceOf(ArrayBuffer);
  });

  it("retries a CDN face after a transient failure instead of falling back", async () => {
    const calls: Captured[] = [];
    class FailingFace {
      constructor(
        public family: string,
        public source: string | ArrayBuffer,
      ) {
        calls.push({ family, source });
      }
      load() {
        return Promise.reject(new Error("network down"));
      }
    }
    vi.stubGlobal("FontFace", FailingFace);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );
    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: { add: vi.fn(), delete: vi.fn() },
    });

    injectFontFace("Blip Sans");
    await vi.waitFor(() =>
      expect((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1),
    );
    await new Promise((r) => setTimeout(r, 0));
    expect(calls.every((c) => typeof c.source === "string")).toBe(true);
    injectFontFace("Blip Sans");
    expect(calls.length).toBe(2);
  });
});
