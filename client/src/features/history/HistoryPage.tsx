import { useEffect, useState } from "react";
import { LayoutGrid } from "lucide-react";
import { useGenerations, type HistoryFilter } from "@/api/generations";
import { flattenPages } from "@/api/pagination";
import { Button } from "@/components/ui/button";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { injectBrandFontFaces } from "@/styles/brandFonts";
import { cn } from "@/lib/utils";
import type { Generation } from "@/types";
import { DetailDialog } from "./DetailDialog";
import { HistoryCard } from "./HistoryCard";

const FILTERS: { value: HistoryFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "post_pack", label: "LinkedIn" },
  { value: "text", label: "Posts" },
  { value: "card", label: "Cards" },
  { value: "document", label: "Documents" },
];

export function HistoryPage() {
  const { workspace, workspaceId } = useActiveWorkspace();
  const brand = workspace?.brand_profile ?? null;
  const [filter, setFilter] = useState<HistoryFilter>("all");
  const { data, isLoading, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useGenerations(workspaceId, filter);
  const generations = flattenPages(data);
  const [open, setOpen] = useState<Generation | null>(null);

  // Load workspace fonts so card thumbnails render in the brand type.
  useEffect(() => {
    if (brand) injectBrandFontFaces(brand.fonts);
  }, [brand]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4 animate-fade-in-up">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
            Content History
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-[-0.01em] text-foreground">
            Generations
          </h1>
        </div>
        <div className="flex gap-1 rounded-md border border-border bg-surface p-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={cn(
                "rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
                filter === f.value
                  ? "bg-surface-variant text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </header>

      {isLoading && <SkeletonGrid />}
      {isError && (
        <p className="rounded-lg border border-border bg-surface p-4 text-sm text-destructive">
          Couldn't load history.
        </p>
      )}
      {!isLoading && !isError && generations.length === 0 && <EmptyHistory />}
      {generations.length > 0 && (
        <div className="grid animate-fade-in-up gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {generations.map((gen) => (
            <HistoryCard
              key={gen.id}
              gen={gen}
              brand={brand}
              workspaceId={workspaceId}
              onOpen={() => setOpen(gen)}
            />
          ))}
        </div>
      )}
      {hasNextPage && (
        <div className="flex justify-center">
          <Button variant="secondary" onClick={() => fetchNextPage()} loading={isFetchingNextPage}>
            Load more
          </Button>
        </div>
      )}

      <DetailDialog
        gen={open}
        brand={brand}
        workspaceId={workspaceId}
        onClose={() => setOpen(null)}
      />
    </div>
  );
}

function EmptyHistory() {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-surface-variant text-muted-foreground">
        <LayoutGrid className="h-5 w-5" aria-hidden />
      </span>
      <p className="mt-4 text-sm font-medium text-foreground">No generations yet</p>
      <p className="mt-1 max-w-xs text-sm text-muted-foreground">
        Generated posts, cards, and documents land here, with their retrieval snapshot.
      </p>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className="h-40 animate-pulse rounded-lg border border-border bg-surface-variant/40"
        />
      ))}
    </div>
  );
}
