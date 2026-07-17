import { useEffect, useRef, useState } from "react";
import { ImageOff, Sparkles, Trash2, Upload } from "lucide-react";
import { fetchImageDataUrl } from "@/api/images";
import { useAddExemplar, useRemoveExemplar } from "@/api/workspaces";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth";
import type { BrandExemplar, Workspace } from "@/types";
import { canAddExemplar, MAX_EXEMPLARS } from "./exemplars";

/** Settings → Example cards (Phase 4c). Upload past brand cards; each is sent to
 *  Claude vision once, which proposes a short style note stored on the workspace
 *  and injected into generation. Persists immediately (like the logo); disabled
 *  for the demo user and at the cap. */
export function ExemplarsSection({ workspace }: { workspace: Workspace }) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const add = useAddExemplar(workspace.id);
  const remove = useRemoveExemplar(workspace.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const exemplars = workspace.brand_profile.exemplars ?? [];

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(null);
    try {
      await add.mutateAsync(file);
    } catch {
      setError("Couldn’t add that card. Use a JPG, PNG, or WebP under 8 MB.");
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="eyebrow">
          Example cards · {exemplars.length} of {MAX_EXEMPLARS}
        </span>
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={onFile}
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => fileRef.current?.click()}
          loading={add.isPending}
          disabled={!canAddExemplar(exemplars.length, isDemo)}
          title={isDemo ? "Disabled in the demo" : undefined}
        >
          <Upload className="h-4 w-4" aria-hidden />
          Add example card
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Upload past on-brand cards — each is analyzed once to steer new copy toward your style.
      </p>
      {add.isPending && (
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 animate-pulse" aria-hidden />
          Reading the card…
        </span>
      )}
      {error && <span className="text-xs text-destructive">{error}</span>}
      {exemplars.length === 0 ? (
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          <ImageOff className="h-4 w-4" aria-hidden />
          No example cards yet.
        </span>
      ) : (
        <ul className="flex flex-col gap-3">
          {exemplars.map((ex) => (
            <ExemplarRow
              key={ex.id}
              exemplar={ex}
              isDemo={isDemo}
              removing={remove.isPending}
              onRemove={() => remove.mutate(ex.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ExemplarRow({
  exemplar,
  isDemo,
  removing,
  onRemove,
}: {
  exemplar: BrandExemplar;
  isDemo: boolean;
  removing: boolean;
  onRemove: () => void;
}) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    if (!exemplar.url) return;
    fetchImageDataUrl(exemplar.url)
      .then((d) => alive && setDataUrl(d))
      .catch(() => alive && setDataUrl(null));
    return () => {
      alive = false;
    };
  }, [exemplar.url]);

  return (
    <li className="flex items-start gap-3 rounded-md border border-border p-2.5">
      <div className="flex h-16 w-[51px] shrink-0 items-center justify-center overflow-hidden rounded bg-surface-variant">
        {dataUrl ? (
          <img src={dataUrl} alt="" className="max-h-full max-w-full object-contain" />
        ) : (
          <span className="h-4 w-4 animate-pulse rounded bg-muted-foreground/30" aria-hidden />
        )}
      </div>
      <p className="flex-1 text-sm leading-relaxed text-foreground">{exemplar.style_note}</p>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        onClick={onRemove}
        loading={removing}
        disabled={isDemo}
        title={isDemo ? "Disabled in the demo" : "Remove"}
        aria-label="Remove example card"
        className="hover:text-destructive"
      >
        <Trash2 className="h-4 w-4" aria-hidden />
      </Button>
    </li>
  );
}
