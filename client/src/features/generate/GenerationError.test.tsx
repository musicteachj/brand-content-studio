import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { GenerationError } from "./GenerationError";

function renderError(code?: string | null) {
  render(
    <MemoryRouter>
      <GenerationError message="Nope." code={code} />
    </MemoryRouter>,
  );
}

describe("GenerationError", () => {
  it.each(["live_ai_paused", "visitor_allowance", "live_ai_unavailable", "rate_limited"])(
    "links to the examples for %s",
    (code) => {
      renderError(code);
      expect(screen.getByRole("alert")).toHaveTextContent("Nope.");
      expect(screen.getByRole("link", { name: "Browse the ready-made examples" })).toHaveAttribute(
        "href",
        "/examples",
      );
    },
  );

  it("shows no examples link for other errors", () => {
    renderError("example_read_only");
    expect(screen.getByRole("alert")).toHaveTextContent("Nope.");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows no link without a code, and a fallback without a message", () => {
    render(
      <MemoryRouter>
        <GenerationError message={null} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Generation failed.");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
