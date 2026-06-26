import { useCallback, useRef, useState } from "react";
import { streamDocumentGeneration, type DocumentStreamBody } from "@/lib/sse";
import type {
  DocumentArchetype,
  DocumentFormat,
  DocumentFormatRef,
  DocumentModel,
  RetrievalEnvelope,
} from "@/types";

type Status = "idle" | "streaming" | "done" | "error";

interface State {
  status: Status;
  text: string; // the streamed draft, shown while drafting
  document: DocumentModel | null; // the structured model (terminal meta)
  archetype: DocumentArchetype;
  formats: Partial<Record<DocumentFormat, DocumentFormatRef>>;
  generationId: string | null;
  retrieval: RetrievalEnvelope | null;
  error: string | null;
}

const INITIAL: State = {
  status: "idle",
  text: "",
  document: null,
  archetype: "one-pager",
  formats: {},
  generationId: null,
  retrieval: null,
  error: null,
};

/** Drives a single streamed document generation: the draft streams as text for
 *  the live preview, then the terminal meta delivers the structured model and the
 *  per-format storage keys (the files were built server-side). */
export function useDocumentGeneration(workspaceId: string | null) {
  const [state, setState] = useState<State>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const generate = useCallback(
    async (body: DocumentStreamBody) => {
      if (!workspaceId) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setState({ ...INITIAL, status: "streaming", archetype: body.archetype as DocumentArchetype });

      let errored = false;
      await streamDocumentGeneration(
        workspaceId,
        body,
        {
          onText: (delta) => setState((s) => ({ ...s, text: s.text + delta })),
          onMeta: (meta) =>
            setState((s) => ({
              ...s,
              document: meta.document,
              archetype: meta.archetype,
              formats: meta.formats,
              generationId: meta.generation_id,
              retrieval: meta.retrieval,
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
