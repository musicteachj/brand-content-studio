import { useRef, type KeyboardEvent } from "react";

/** ARIA radiogroup keyboard support (A11Y-04). Our radiogroups are custom
 *  `role="radiogroup"` + `role="radio"` <button>s, which need roving tabindex (one
 *  tab stop) and arrow-key navigation to honor the ARIA contract. Spread
 *  `radioProps(i)` onto each radio button; click selection is unchanged.
 *
 *  `selectedIndex` is -1 when nothing is selected yet (the first radio becomes the
 *  single tab stop, and arrows select from there). */
export function useRovingRadio(
  count: number,
  selectedIndex: number,
  onSelect: (index: number) => void,
) {
  const refs = useRef<(HTMLElement | null)[]>([]);
  const focusIndex = selectedIndex >= 0 ? selectedIndex : 0;

  function radioProps(index: number) {
    return {
      tabIndex: index === focusIndex ? 0 : -1,
      ref: (el: HTMLElement | null) => {
        refs.current[index] = el;
      },
      onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
        let target: number;
        if (e.key === "ArrowLeft" || e.key === "ArrowUp") target = (index - 1 + count) % count;
        else if (e.key === "ArrowRight" || e.key === "ArrowDown") target = (index + 1) % count;
        else return;
        e.preventDefault();
        onSelect(target);
        refs.current[target]?.focus();
      },
    };
  }

  return { radioProps };
}
