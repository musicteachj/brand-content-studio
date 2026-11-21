import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// The locked-SVG hook and the rasterizer are stubbed so a test can put the
// preview into any export state without running Satori or resvg.
const exportState = vi.hoisted(() => ({
  svg: { svg: null as string | null, error: null as string | null, loading: false },
  pngError: null as unknown,
}));
vi.mock("@/features/generate/useCardExport", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/generate/useCardExport")>();
  return {
    ...actual,
    useCardSvg: () => exportState.svg,
    svgToPng: async () => {
      if (exportState.pngError) throw exportState.pngError;
      return new Blob(["png"], { type: "image/png" });
    },
  };
});

import { CardPreview } from "./CardPreview";
import { CARD_EXPORT_FAILED_COPY, CardExportError } from "./cardExportError";
import { makeBrandProfile } from "@/test/factories";

let container: HTMLDivElement;
let root: Root;

function render(props: Partial<React.ComponentProps<typeof CardPreview>> = {}) {
  const onAddImage = vi.fn();
  const onClearImage = vi.fn();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root.render(
      <CardPreview
        // done + fields:null keeps the finishing-actions row up while rendering no
        // ScaledCardBox (ResizeObserver) and never invoking Satori (lockedReady=false).
        status="done"
        copy=""
        template="photo-led"
        fields={null}
        brand={makeBrandProfile()}
        accentHex={null}
        imageDataUrl="data:img"
        attribution={null}
        error={null}
        hasImage
        imageError={null}
        onAddImage={onAddImage}
        onClearImage={onClearImage}
        {...props}
      />,
    ),
  );
  return { onAddImage, onClearImage };
}

function buttonWith(label: string): HTMLButtonElement | undefined {
  return [...container.querySelectorAll("button")].find((b) =>
    b.textContent?.toLowerCase().includes(label.toLowerCase()),
  );
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  exportState.svg = { svg: null, error: null, loading: false };
  exportState.pngError = null;
});

describe("CardPreview — remove image (ARCH-04)", () => {
  it("shows a Remove control when an image is present and calls onClearImage", () => {
    const { onClearImage } = render({ hasImage: true });
    const remove = buttonWith("remove");
    expect(remove).toBeTruthy();
    act(() => remove!.click());
    expect(onClearImage).toHaveBeenCalledTimes(1);
  });

  it("shows no Remove control when there is no image", () => {
    render({ hasImage: false });
    expect(buttonWith("remove")).toBeUndefined();
    // ...but still offers to add one.
    expect(buttonWith("add an image")).toBeTruthy();
  });
});

describe("CardPreview: export errors read plainly", () => {
  function alerts(): string[] {
    return [...container.querySelectorAll('[role="alert"]')].map((el) => el.textContent ?? "");
  }

  it("shows the locked-SVG error next to the disabled Export button", () => {
    exportState.svg = { svg: null, error: CARD_EXPORT_FAILED_COPY, loading: false };
    render();
    expect(buttonWith("export png")?.disabled).toBe(true);
    expect(alerts()).toContain(CARD_EXPORT_FAILED_COPY);
  });

  it("maps a raw export failure to the plain constant", async () => {
    exportState.svg = { svg: "<svg/>", error: null, loading: false };
    exportState.pngError = new Error("Aborted(CompileError: WebAssembly.instantiate())");
    render();
    await act(async () => buttonWith("export png")!.click());
    expect(alerts()).toEqual([CARD_EXPORT_FAILED_COPY]);
  });

  it("keeps a curated export message", async () => {
    exportState.svg = { svg: "<svg/>", error: null, loading: false };
    exportState.pngError = new CardExportError("Could not load the workspace brand fonts.");
    render();
    await act(async () => buttonWith("export png")!.click());
    expect(alerts()).toEqual(["Could not load the workspace brand fonts."]);
  });
});

describe("CardPreview errors", () => {
  it("stays quiet when the error is shown beside it (LinkedIn Post mode)", () => {
    render({ status: "error", error: "Something went wrong.", errorShownBeside: true });
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.textContent).toContain("No card this time.");
    expect(container.textContent).not.toContain("Something went wrong.");
  });
});

describe("CardPreview: linked Unsplash credit", () => {
  const ATTRIBUTION = {
    author: "Jane Mason",
    author_url: "https://unsplash.com/@janemason?utm_source=Folio&utm_medium=referral",
    source_url: "https://unsplash.com/photos/abc123?utm_source=Folio&utm_medium=referral",
  };
  const FIELDS = { eyebrow: "", headline: "Walls that breathe", body: "", cta: "", hashtag: "" };

  // A finished card shown as its locked SVG (no Satori, no ScaledCardBox).
  function renderFinished(props: Partial<React.ComponentProps<typeof CardPreview>> = {}) {
    exportState.svg = { svg: "<svg/>", error: null, loading: false };
    render({ fields: FIELDS, attribution: ATTRIBUTION, ...props });
  }

  function credit(): HTMLParagraphElement | undefined {
    return [...container.querySelectorAll("p")].find((p) => p.textContent?.startsWith("Photo by"));
  }

  it("links the photographer and Unsplash under a finished photo card", () => {
    renderFinished();
    const p = credit();
    expect(p?.textContent).toBe("Photo by Jane Mason on Unsplash");
    const [author, unsplash] = [...p!.querySelectorAll("a")];
    expect(author.getAttribute("href")).toBe(ATTRIBUTION.author_url);
    expect(unsplash.getAttribute("href")).toBe(
      "https://unsplash.com/?utm_source=Folio&utm_medium=referral",
    );
    for (const link of [author, unsplash]) {
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noreferrer");
    }
  });

  it("shows no credit without an Unsplash photo", () => {
    renderFinished({ attribution: null });
    expect(credit()).toBeUndefined();
  });

  it("shows no credit on a layout that does not use the photo", () => {
    renderFinished({ template: "statement" });
    expect(credit()).toBeUndefined();
  });

  it("shows no credit before the card is finished", () => {
    render({ status: "idle", fields: FIELDS, attribution: ATTRIBUTION });
    expect(credit()).toBeUndefined();
  });

  it("shows a saved author link that is not on unsplash.com as plain text", () => {
    renderFinished({
      attribution: { ...ATTRIBUTION, author_url: "https://example.com/@janemason" },
    });
    const p = credit();
    expect(p?.textContent).toBe("Photo by Jane Mason on Unsplash");
    const links = [...p!.querySelectorAll("a")];
    expect(links).toHaveLength(1);
    expect(links[0].textContent).toBe("Unsplash");
  });
});
