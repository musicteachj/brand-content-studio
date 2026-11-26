import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BrandProfile, CardPreset } from "@/types";
import { CardControlsPanel } from "./CardControlsPanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const BRAND: BrandProfile = {
  colors: [{ name: "Ink", hex: "#1C3A2E", role: "primary" }],
  accent_hex: null,
  fonts: { heading: null, body: null, mono: null },
  logo: null,
  voice_summary: null,
  exemplars: [],
  brand_images: [],
  uploaded_fonts: [],
  card_presets: [],
};

const PRESET: CardPreset = {
  id: "p1",
  name: "Bold quote",
  template_id: "quote",
  accent_hex: "#1C3A2E",
};

let container: HTMLDivElement;
let root: Root;

function mount(props: Partial<React.ComponentProps<typeof CardControlsPanel>>) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root.render(
      <CardControlsPanel
        brand={BRAND}
        brief=""
        setBrief={() => {}}
        tone="default"
        setTone={() => {}}
        template={null}
        setTemplate={() => {}}
        presets={[]}
        onApplyPreset={() => {}}
        isStreaming={false}
        hasGenerated={false}
        onGenerate={() => {}}
        onStop={() => {}}
        {...props}
      />,
    ),
  );
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("CardControlsPanel presets", () => {
  it("hides the preset picker when there are no presets", () => {
    mount({ presets: [] });
    expect(container.querySelector("#card-preset")).toBeNull();
  });

  it("applies a preset when one is chosen", () => {
    const onApplyPreset = vi.fn();
    mount({ presets: [PRESET], onApplyPreset });
    const select = container.querySelector<HTMLSelectElement>("#card-preset");
    expect(select).not.toBeNull();
    const proto = Object.getPrototypeOf(select!);
    const setValue = Object.getOwnPropertyDescriptor(proto, "value")!.set!;
    act(() => {
      setValue.call(select, "p1");
      select!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(onApplyPreset).toHaveBeenCalledWith(PRESET);
  });
});

// QA-08: Generate stayed disabled after a brief with no layout, and never said why.
describe("CardControlsPanel layout hint", () => {
  const generateButton = () =>
    [...container.querySelectorAll("button")].find((b) =>
      /generate card/i.test(b.textContent ?? ""),
    );

  it("says to pick a layout when the brief is ready but no layout is chosen", () => {
    mount({ brief: "Why hempcrete", template: null });
    expect(generateButton()?.disabled).toBe(true);
    expect(container.textContent).toContain("Pick a layout above to generate.");
  });

  it("drops the hint once a layout is chosen", () => {
    mount({ brief: "Why hempcrete", template: "quote" });
    expect(generateButton()?.disabled).toBe(false);
    expect(container.textContent).not.toContain("Pick a layout above");
  });
});
