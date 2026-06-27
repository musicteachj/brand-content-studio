import { useCallback, useEffect, useRef, useState } from "react";
import { streamTextGeneration, type TextStreamBody } from "@/lib/sse";
import type { SSEMetaFrame } from "@/types";

type Status = "idle" | "streaming" | "done" | "error";
type Retrieval = SSEMetaFrame["meta"]["retrieval"];

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

/** Drives a single streamed text-post generation: accumulates tokens, captures
 *  the terminal retrieval meta, and exposes abort. */
export function useTextGeneration(workspaceId: string | null) {
  const [state, setState] = useState<State>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  // Switching workspaces must not leave an in-flight stream writing into the new
  // workspace's view: abort it and reset to a clean slate.
  useEffect(() => {
    setState(INITIAL);
    return () => abortRef.current?.abort();
  }, [workspaceId]);

  const generate = useCallback(
    async (body: TextStreamBody) => {
      if (!workspaceId) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setState({ ...INITIAL, status: "streaming" });

      let errored = false;
      await streamTextGeneration(
        workspaceId,
        body,
        {
          onText: (delta) => setState((s) => ({ ...s, text: s.text + delta })),
          onMeta: (meta) =>
            setState((s) => ({
              ...s,
              retrieval: meta.retrieval,
              generationId: meta.generation_id,
            })),
          onError: (message) => {
            errored = true;
            setState((s) => ({ ...s, status: "error", error: message }));
          },
        },
        controller.signal,
      );

      if (!controller.signal.aborted) {
        setState((s) => (errored ? s : { ...s, status: "done" }));
      }
    },
    [workspaceId],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => (s.status === "streaming" ? { ...s, status: "done" } : s));
  }, []);

  return { ...state, generate, stop };
}
