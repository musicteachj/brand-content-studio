import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

import { CardPreview } from "./CardPreview";
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
