import { create } from "zustand";
import type { Generation } from "@/types";

/** Ephemeral hand-off from History → Generate: a card generation to load into the
 *  editor for customization (layout/accent/copy edits, image swap), with no model
 *  call. Not persisted — it's consumed once on the Generate page then cleared. */
interface GenerateState {
  hydrate: Generation | null;
  setHydrate: (g: Generation | null) => void;
}

export const useGenerateStore = create<GenerateState>((set) => ({
  hydrate: null,
  setHydrate: (hydrate) => set({ hydrate }),
}));
