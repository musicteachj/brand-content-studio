import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TemplatePicker } from "./TemplatePicker";
import { makeBrandProfile } from "@/test/factories";

describe("TemplatePicker keyboard nav (A11Y-04)", () => {
  it("uses roving tabindex and moves selection with arrow keys (incl. wrap-around)", async () => {
    const onChange = vi.fn();
    render(<TemplatePicker brand={makeBrandProfile()} value="photo-led" onChange={onChange} />);

    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
    // The selected radio is the single tab stop; the rest are -1.
    expect(radios[0]).toHaveAttribute("tabindex", "0");
    expect(radios[1]).toHaveAttribute("tabindex", "-1");
    expect(radios[2]).toHaveAttribute("tabindex", "-1");

    radios[0].focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("statement");

    onChange.mockClear();
    radios[0].focus();
    await userEvent.keyboard("{ArrowLeft}"); // wraps to the last
    expect(onChange).toHaveBeenCalledWith("quote");
  });
});
