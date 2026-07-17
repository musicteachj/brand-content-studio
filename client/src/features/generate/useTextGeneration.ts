import { streamTextGeneration, type TextStreamBody } from "@/lib/sse";
import type { SSEMetaFrame } from "@/types";
import { useStreamedGeneration, type Status } from "./useStreamedGeneration";

type Meta = SSEMetaFrame["meta"];
type Retrieval = Meta["retrieval"];

interface State {
  status: Status;
  text: string;
  retrieval: Retrieval | null;
  generationId: string | null;
  error: string | null;
}

const INITIAL: State = {
  status: "idle",
  text: "",
  retrieval: null,
  generationId: null,
  error: null,
};

/** Drives a single streamed text-post generation: accumulates tokens, captures the
 *  terminal retrieval meta, and exposes abort — a thin composition over the shared
 *  streaming state machine (ARCH-04). */
export function useTextGeneration(workspaceId: string | null) {
  const { state, generate, stop } = useStreamedGeneration<State, TextStreamBody, Meta>(
    workspaceId,
    {
      initial: INITIAL,
      stream: streamTextGeneration,
      applyText: (s, delta) => ({ ...s, text: s.text + delta }),
      applyMeta: (s, meta) => ({
        ...s,
        retrieval: meta.retrieval,
        generationId: meta.generation_id,
      }),
    },
  );
  return { ...state, generate, stop };
}
