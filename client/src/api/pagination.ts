/** Flatten react-query infinite-query pages into a single list. */
export function flattenPages<T>(data?: { pages: { items: T[] }[] }): T[] {
  return data?.pages.flatMap((p) => p.items) ?? [];
}
