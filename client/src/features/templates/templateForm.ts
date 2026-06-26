/** A blank value for each placeholder. */
export function emptyValues(placeholders: string[]): Record<string, string> {
  return Object.fromEntries(placeholders.map((p) => [p, ""]));
}

/** Apply filled values (e.g. an AI draft) onto the known placeholders only,
 *  leaving unknown keys out and missing ones blank. */
export function mergeFilled(
  placeholders: string[],
  filled: Record<string, string>,
): Record<string, string> {
  return Object.fromEntries(placeholders.map((p) => [p, filled[p] ?? ""]));
}
