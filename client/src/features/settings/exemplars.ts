// Mirrors the server cap (workspace_service.MAX_EXEMPLARS).
export const MAX_EXEMPLARS = 5;

/** Whether the "Add example card" control is enabled. */
export function canAddExemplar(count: number, isDemo: boolean): boolean {
  return !isDemo && count < MAX_EXEMPLARS;
}
