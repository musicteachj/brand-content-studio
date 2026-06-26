import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { CARD_H, CARD_W } from "@/features/generate/cards/cardElement";

/** Sizes a native 1080×1350 card element down to fit the available width via a
 *  CSS transform (Satori-subset elements use fixed px, so scaling is the way to
 *  fit them responsively). Used by the live preview, the export fallback, and the
 *  history thumbnail. */
export function ScaledCardBox({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.4);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setScale(el.clientWidth / CARD_W);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // The inner card is the native 1080×1350 scaled with a transform. Transforms
  // don't shrink layout box size, so the inner div is absolutely positioned (out of
  // flow) and the outer box is clipped — the box height then comes purely from the
  // 4:5 aspect ratio instead of the un-scaled 1350px height.
  return (
    <div
      ref={ref}
      style={{
        position: "relative",
        width: "100%",
        aspectRatio: `${CARD_W} / ${CARD_H}`,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: CARD_W,
          height: CARD_H,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
        }}
      >
        {children}
      </div>
    </div>
  );
}
