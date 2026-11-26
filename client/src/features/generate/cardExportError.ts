// Card PNG export errors a visitor can read. Satori, harfbuzz, and resvg fail
// with raw engine text (an Emscripten "Aborted(CompileError: ...)", for one), so
// only messages we wrote ourselves, marked with CardExportError, reach the page;
// anything else shows one plain constant.

export const CARD_EXPORT_FAILED_COPY =
  "We couldn't make the PNG just now. Try again, or reload the page.";

/** An export failure whose message is curated copy, safe to show as is. */
export class CardExportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CardExportError";
  }
}

/** The message to show for a failed card render or PNG export. */
export function cardExportErrorMessage(err: unknown): string {
  return err instanceof CardExportError ? err.message : CARD_EXPORT_FAILED_COPY;
}
