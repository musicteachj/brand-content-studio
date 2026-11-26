import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, LayoutGrid } from "lucide-react";
import { exampleBrandProfile, exampleDownloadUrl, useExamples } from "@/api/examples";
import { Brand } from "@/components/Brand";
import { Button } from "@/components/ui/button";
import { DetailDialog } from "@/features/history/DetailDialog";
import { HistoryCard } from "@/features/history/HistoryCard";
import { useAuthStore } from "@/stores/auth";
import { injectBrandFontFaces } from "@/styles/brandFonts";
import type { ExampleBrand, Generation } from "@/types";

/** The public examples at /examples: the demo brand's ready-made generations, readable
 *  with no demo start and no bot check. Everything is read-only; documents download from
 *  the public examples route. */
export function ExamplesPage() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { data, isLoading, isError, refetch, isRefetching } = useExamples();
  const brand = useMemo(() => (data ? exampleBrandProfile(data.brand) : null), [data]);
  const items = data?.items ?? [];
  const name = data?.workspace_name || "a sample brand";
  const [open, setOpen] = useState<Generation | null>(null);
  // The dialog is controlled, so remember what opened it to hand focus back on close.
  const openerRef = useRef<HTMLElement | null>(null);

  // Load the brand's fonts so cards and documents render in its type, as History does.
  useEffect(() => {
    if (brand) injectBrandFontFaces(brand.fonts);
  }, [brand]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-6 py-6 sm:px-10">
        <Link
          to="/"
          aria-label="Folio home"
          className="rounded-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Brand />
        </Link>
        <Button asChild variant={isAuthenticated ? "ghost" : "primary"} size="sm">
          <Link to="/">
            {isAuthenticated ? (
              <>
                <ArrowLeft className="h-4 w-4" aria-hidden />
                Back to the studio
              </>
            ) : (
              <>
                Try it live
                <ArrowRight className="h-4 w-4" aria-hidden />
              </>
            )}
          </Link>
        </Button>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 pb-20 pt-6 sm:px-10 lg:pt-10">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl animate-fade-in-up">
            <p className="eyebrow text-[11px]">Ready-made examples</p>
            <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-heading text-foreground sm:text-4xl">
              What Folio made for {name}
            </h1>
            <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
              Each piece was written from the brand’s own guidelines and past posts. Open one to see
              the brand material it drew on, or download the document.
            </p>
          </div>
          {data && <BrandSummary brand={data.brand} />}
        </div>

        <div className="mt-10">
          {isLoading && <SkeletonGrid />}
          {isError && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface p-4">
              <p role="alert" className="text-sm text-destructive">
                Couldn’t load the examples.
              </p>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refetch()}
                loading={isRefetching}
              >
                Try again
              </Button>
            </div>
          )}
          {data && items.length === 0 && <NoExamples />}
          {items.length > 0 && (
            <div className="grid animate-fade-in-up gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {items.map((gen) => (
                <HistoryCard
                  key={gen.id}
                  gen={gen}
                  brand={brand}
                  workspaceId={null}
                  readOnly
                  downloadUrl={exampleDownloadUrl(gen.id)}
                  onOpen={(opener) => {
                    openerRef.current = opener;
                    setOpen(gen);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </main>

      <DetailDialog
        gen={open}
        brand={brand}
        workspaceId={null}
        readOnly
        downloadUrl={open ? exampleDownloadUrl(open.id) : undefined}
        onClose={() => setOpen(null)}
        returnFocusTo={openerRef}
      />
    </div>
  );
}

/** The brand the examples were written for: its palette and its voice, in a quiet panel. */
function BrandSummary({ brand }: { brand: ExampleBrand }) {
  if (brand.colors.length === 0 && !brand.voice_summary) return null;
  return (
    <aside
      aria-label="The brand"
      className="w-full max-w-sm shrink-0 animate-fade-in-up rounded-lg border border-border bg-surface p-4 shadow-light"
    >
      <p className="eyebrow">The brand</p>
      {brand.colors.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {brand.colors.map((c) => (
            <li key={`${c.role}-${c.hex}`} className="flex items-center gap-1.5">
              {/* The brand's own color, from the data: not a Folio token. */}
              <span
                className="h-4 w-4 rounded-full border border-border"
                style={{ backgroundColor: c.hex }}
                aria-hidden
              />
              <span className="text-xs text-muted-foreground">{c.name}</span>
            </li>
          ))}
        </ul>
      )}
      {brand.voice_summary && (
        <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-foreground">
          {brand.voice_summary}
        </p>
      )}
    </aside>
  );
}

function NoExamples() {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-surface-variant text-muted-foreground">
        <LayoutGrid className="h-5 w-5" aria-hidden />
      </span>
      <p className="mt-4 text-sm font-medium text-foreground">The examples aren’t ready yet</p>
      <p className="mt-1 max-w-xs text-sm text-muted-foreground">
        They appear once the demo brand is set up. Try again in a minute.
      </p>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="h-64 animate-pulse rounded-lg border border-border bg-surface-variant/40"
        />
      ))}
    </div>
  );
}
