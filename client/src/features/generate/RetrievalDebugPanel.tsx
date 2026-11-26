import { Database, Pin } from "lucide-react";
import type { RetrievalMetaItem } from "@/types";

interface Retrieval {
  k?: number;
  retrieved: RetrievalMetaItem[];
  embedding_model: string;
  latency_ms?: number; // omitted for re-opened history (not persisted)
}

/** The proof the RAG loop works (DESIGN: "precise, trustworthy tooling — no
 *  glow"). Each source shows a score bar and a peek of the matched text. */
export function RetrievalDebugPanel({ retrieval }: { retrieval: Retrieval | null }) {
  return (
    <aside className="rounded-lg border border-border bg-surface shadow-light">
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Database className="h-4 w-4 text-muted-foreground" aria-hidden />
        <h2 className="text-sm font-semibold text-foreground">Retrieved context</h2>
        {retrieval && (
          <span className="ml-auto eyebrow">
            {retrieval.retrieved.length} chunks
            {retrieval.latency_ms != null ? ` · ${retrieval.latency_ms}ms` : ""}
          </span>
        )}
      </header>

      {!retrieval ? (
        <p className="px-4 py-6 text-sm text-muted-foreground">
          Generate a post to see which brand chunks were retrieved, with similarity scores.
        </p>
      ) : (
        <>
          <ul className="divide-y divide-border">
            {retrieval.retrieved.map((item) => (
              <ChunkRow key={item.chunk_id} item={item} />
            ))}
          </ul>
          <footer className="border-t border-border px-4 py-2.5">
            <p className="eyebrow">
              {retrieval.embedding_model}
              {retrieval.k != null ? ` · k=${retrieval.k}` : ""}
            </p>
          </footer>
        </>
      )}
    </aside>
  );
}

function ChunkRow({ item }: { item: RetrievalMetaItem }) {
  const pct = Math.max(0, Math.min(100, Math.round(item.score * 100)));
  return (
    <li className="px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="truncate text-xs font-medium text-foreground">{item.filename}</span>
        <span className="shrink-0 rounded-sm bg-surface-variant px-1.5 py-0.5 eyebrow text-3xs">
          {item.asset_kind}
        </span>
        {item.page != null && <span className="shrink-0 eyebrow text-3xs">p.{item.page}</span>}
        {item.pinned ? (
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 eyebrow text-3xs">
            <Pin className="h-3 w-3" aria-hidden /> Pinned
          </span>
        ) : (
          <span className="ml-auto shrink-0 font-mono text-2xs tabular-nums text-muted-foreground">
            {item.score.toFixed(3)}
          </span>
        )}
      </div>

      {!item.pinned && (
        // Data-viz fill, not an action — accent is reserved for actions (DESIGN §7).
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-surface-variant">
          <div
            className="h-full rounded-full bg-muted-foreground"
            style={{ width: `${pct}%` }}
            aria-hidden
          />
        </div>
      )}

      <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
        {item.preview}
      </p>
    </li>
  );
}
