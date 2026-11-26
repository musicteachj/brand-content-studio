import { create } from "zustand";
import { persist } from "zustand/middleware";

/** The active workspace id. Phase 1a is single-workspace per user (the seeded
 *  Verdure workspace for the demo), but this keeps the door open for more. */
interface WorkspaceState {
  activeId: string | null;
  setActive: (id: string | null) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      activeId: null,
      setActive: (id) => set({ activeId: id }),
    }),
    { name: "folio-workspace" },
  ),
);
