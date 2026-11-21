import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { GenerationError } from "./GenerationError";

function renderError(message: string | null) {
  render(
    <MemoryRouter>
      <GenerationError message={message} />
    </MemoryRouter>,
  );
}

describe("GenerationError", () => {
  it.each([
    "Live AI is paused for today.",
    "Something went wrong. Please try again. (ref: abc123)",
    "Folio couldn't reach its server just now. Try again in a minute.",
  ])("links to the examples for %s", (message) => {
    renderError(message);
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("link", { name: "Browse the ready-made examples" })).toHaveAttribute(
      "href",
      "/examples",
    );
  });

  it("shows a fallback without a message, still with the examples link", () => {
    renderError(null);
    expect(screen.getByRole("alert")).toHaveTextContent("Generation failed.");
    expect(
      screen.getByRole("link", { name: "Browse the ready-made examples" }),
    ).toBeInTheDocument();
  });
});
