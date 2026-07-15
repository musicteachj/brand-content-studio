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
});
