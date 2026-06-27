// Mirrors the server cap (workspace_service.MAX_BRAND_IMAGES).
export const MAX_BRAND_IMAGES = 24;

/** Whether the "Add image" control is enabled. */
export function canAddBrandImage(count: number, isDemo: boolean): boolean {
  return !isDemo && count < MAX_BRAND_IMAGES;
}
