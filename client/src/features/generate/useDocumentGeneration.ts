import { streamDocumentGeneration, type DocumentStreamBody } from "@/lib/sse";
import type {
  DocumentArchetype,
  DocumentFormat,
  DocumentFormatRef,
  DocumentModel,
  RetrievalEnvelope,
  SSEDocumentMetaFrame,
} from "@/types";
import { useStreamedGeneration, type Status } from "./useStreamedGeneration";

type Meta = SSEDocumentMetaFrame["meta"];

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

/** Drives a single streamed document generation: the draft streams as text for the
 *  live preview, then the terminal meta delivers the structured model and the
 *  per-format storage keys. A thin composition over the shared streaming machine. */
export function useDocumentGeneration(workspaceId: string | null) {
  const { state, generate, stop } = useStreamedGeneration<State, DocumentStreamBody, Meta>(
    workspaceId,
    {
      initial: INITIAL,
      stream: streamDocumentGeneration,
      streamingSeed: (_s, body) => ({
        ...INITIAL,
        status: "streaming",
        archetype: body.archetype as DocumentArchetype,
      }),
      applyText: (s, delta) => ({ ...s, text: s.text + delta }),
      applyMeta: (s, meta) => ({
        ...s,
        document: meta.document,
        archetype: meta.archetype,
        formats: meta.formats,
        generationId: meta.generation_id,
        retrieval: meta.retrieval,
      }),
    },
  );
  return { ...state, generate, stop };
}
