import { useEffect, useRef, useState } from "react";
import { AxiosError } from "axios";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, Trash2, UploadCloud } from "lucide-react";
import { useAssets, useDeleteAsset, useReingestAsset, useUploadAsset } from "@/api/assets";
import { flattenPages } from "@/api/pagination";
import { DemoNotice } from "@/components/DemoNotice";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { StatusPill } from "@/features/assets/StatusPill";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { useAuthStore } from "@/stores/auth";
import type { Asset, AssetKind } from "@/types";

const KIND_OPTIONS: { value: AssetKind; label: string }[] = [
  { value: "voice", label: "Voice & tone" },
  { value: "posts", label: "Past posts" },
  { value: "pillars", label: "Content pillars" },
  { value: "personas", label: "Audience personas" },
  { value: "competitors", label: "Competitors" },
  { value: "other", label: "Other" },
];

const ACCEPT = ".pdf,.md,.markdown,.txt";
const MAX_BYTES = 10 * 1024 * 1024;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function AssetsPage() {
  const { workspaceId } = useActiveWorkspace();
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const { data, isLoading, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useAssets(workspaceId);
  const assets = flattenPages(data);

  // When ingestion finishes (nothing left processing), refresh the workspace
  // counters that the dashboard + corpus-ready gate read from.
  const qc = useQueryClient();
  const wasProcessing = useRef(false);
  const processing = assets.some((a) => a.ingestion_status === "processing");
  useEffect(() => {
    if (wasProcessing.current && !processing) {
      qc.invalidateQueries({ queryKey: ["workspaces"] });
      qc.invalidateQueries({ queryKey: ["workspace", workspaceId] });
    }
    wasProcessing.current = processing;
  }, [processing, qc, workspaceId]);

  return (
    <div className="flex flex-col gap-8">
      <header className="animate-fade-in-up">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
          Asset Manager
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-0.01em] text-foreground">
          Brand corpus
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          Upload brand documents — voice guides, past posts, pillars. Each is parsed, chunked, and
          embedded into this workspace's retrievable corpus.
        </p>
      </header>

      {isDemo ? (
        <DemoNotice message="You're exploring as a demo — the seeded Verdure corpus is read-only. Uploads and deletes are disabled so the demo stays intact. Everything else (generating posts, inspecting retrieval) works." />
      ) : (
        <UploadCard workspaceId={workspaceId} />
      )}

      <section className="animate-fade-in-up" style={{ animationDelay: "60ms" }}>
        <h2 className="mb-3 text-sm font-semibold text-foreground">
          Assets{" "}
          {!isLoading ? <span className="text-muted-foreground">({assets.length})</span> : null}
        </h2>
        {isLoading && <SkeletonRows />}
        {isError && (
          <p className="rounded-lg border border-border bg-surface p-4 text-sm text-destructive">
            Couldn't load assets. Is the server running?
          </p>
        )}
        {!isLoading && !isError && assets.length === 0 && <EmptyAssets />}
        {assets.length > 0 && (
          <ul className="overflow-hidden rounded-lg border border-border">
            {assets.map((asset) => (
              <AssetRow
                key={asset.id}
                asset={asset}
                workspaceId={workspaceId}
                canDelete={!isDemo}
              />
            ))}
          </ul>
        )}
        {hasNextPage && (
          <div className="mt-4 flex justify-center">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => fetchNextPage()}
              loading={isFetchingNextPage}
            >
              Load more
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}

function UploadCard({ workspaceId }: { workspaceId: string | null }) {
  const upload = useUploadAsset(workspaceId);
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<AssetKind>("voice");
  const [error, setError] = useState<string | null>(null);

  function pick(f: File | null) {
    setError(null);
    if (!f) return setFile(null);
    if (f.size > MAX_BYTES) {
      setError("File exceeds the 10 MB limit.");
      return;
    }
    setFile(f);
  }

  async function submit() {
    if (!file) return;
    setError(null);
    try {
      await upload.mutateAsync({ file, assetKind: kind });
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      const detail =
        err instanceof AxiosError && typeof err.response?.data?.detail === "string"
          ? err.response.data.detail
          : "Upload failed.";
      setError(detail);
    }
  }

  return (
    <div className="animate-fade-in-up rounded-lg border border-border bg-surface p-5 shadow-light">
      <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
        <div>
          <Label htmlFor="asset-file">Document</Label>
          <input
            ref={inputRef}
            id="asset-file"
            type="file"
            accept={ACCEPT}
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
            className="block w-full cursor-pointer rounded-sm border border-border bg-surface text-sm text-muted-foreground file:mr-3 file:cursor-pointer file:border-0 file:border-r file:border-border file:bg-surface-variant file:px-3.5 file:py-2.5 file:text-sm file:font-medium file:text-foreground hover:file:bg-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <p className="mt-1.5 text-xs text-muted-foreground">PDF, Markdown, or text · max 10 MB</p>
        </div>
        <div className="w-full sm:w-52">
          <Label htmlFor="asset-kind">Asset kind</Label>
          <Select
            id="asset-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as AssetKind)}
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="mt-4 flex items-center gap-3">
        <Button
          onClick={submit}
          disabled={!file || !workspaceId || upload.isPending}
          loading={upload.isPending}
        >
          <UploadCloud className="h-4 w-4" aria-hidden />
          {upload.isPending ? "Uploading" : "Upload & ingest"}
        </Button>
        {file && !upload.isPending && (
          <span className="truncate text-sm text-muted-foreground">{file.name}</span>
        )}
      </div>
    </div>
  );
}

function AssetRow({
  asset,
  workspaceId,
  canDelete,
}: {
  asset: Asset;
  workspaceId: string | null;
  canDelete: boolean;
}) {
  const del = useDeleteAsset(workspaceId);
  const reingest = useReingestAsset(workspaceId);
  return (
    <li className="flex items-center gap-4 border-b border-border bg-surface-variant/40 px-4 py-3 last:border-b-0">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-surface text-muted-foreground">
        <FileText className="h-4 w-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{asset.filename}</p>
        <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
          {asset.asset_kind} · {formatBytes(asset.size_bytes)}
          {asset.ingestion_status === "ready" && ` · ${asset.chunk_count} chunks`}
        </p>
        {asset.ingestion_status === "error" && asset.error && (
          <p className="mt-1 text-xs text-destructive">{asset.error}</p>
        )}
      </div>
      <StatusPill status={asset.ingestion_status} />
      {asset.ingestion_status === "error" && canDelete && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => reingest.mutate(asset.id)}
          loading={reingest.isPending}
        >
          Retry
        </Button>
      )}
      {canDelete && (
        <button
          type="button"
          onClick={() => del.mutate(asset.id)}
          disabled={del.isPending}
          aria-label={`Delete ${asset.filename}`}
          className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          <Trash2 className="h-4 w-4" aria-hidden />
        </button>
      )}
    </li>
  );
}

function EmptyAssets() {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface p-8 text-center">
      <p className="text-sm font-medium text-foreground">No assets yet</p>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
        Upload a brand document to start building the retrievable corpus.
      </p>
    </div>
  );
}

function SkeletonRows() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-16 animate-pulse rounded-lg border border-border bg-surface-variant/40"
        />
      ))}
    </div>
  );
}
