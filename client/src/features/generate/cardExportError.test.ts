import { describe, expect, it } from "vitest";
import {
  CARD_EXPORT_FAILED_COPY,
  CardExportError,
  cardExportErrorMessage,
} from "./cardExportError";

describe("cardExportErrorMessage", () => {
  it("keeps a curated CardExportError message", () => {
    const err = new CardExportError(
      "Could not load the workspace brand fonts. Check your connection and retry.",
    );
    expect(cardExportErrorMessage(err)).toBe(
      "Could not load the workspace brand fonts. Check your connection and retry.",
    );
  });

  it("replaces a raw error (an Emscripten abort) with the plain constant", () => {
    const raw = new Error(
      "Aborted(CompileError: WebAssembly.instantiate(): expected magic word 00 61 73 6d, found 3c 21 64 6f @+0). Build with -sASSERTIONS for more info.",
    );
    expect(cardExportErrorMessage(raw)).toBe(CARD_EXPORT_FAILED_COPY);
  });

  it("replaces a non-Error rejection with the plain constant", () => {
    expect(cardExportErrorMessage("boom")).toBe(CARD_EXPORT_FAILED_COPY);
    expect(cardExportErrorMessage(undefined)).toBe(CARD_EXPORT_FAILED_COPY);
  });

  it("reads plainly", () => {
    expect(CARD_EXPORT_FAILED_COPY).toBe(
      "We couldn't make the PNG just now. Try again, or reload the page.",
    );
  });
});
