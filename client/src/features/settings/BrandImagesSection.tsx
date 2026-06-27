import { useEffect, useRef, useState } from "react";
import { ImageOff, Trash2, Upload } from "lucide-react";
import { fetchImageDataUrl } from "@/api/images";
import { useAddBrandImage, useRemoveBrandImage } from "@/api/workspaces";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth";
import type { BrandImage, Workspace } from "@/types";
import { canAddBrandImage, MAX_BRAND_IMAGES } from "./brandImages";

/** Settings → Brand images. A reusable library of the workspace's own images;
 *  saved here (no model call) and pickable as a card picture in the image picker.
 *  Persists immediately (like the logo); disabled for the demo user and at the cap. */
export function BrandImagesSection({ workspace }: { workspace: Workspace }) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const add = useAddBrandImage(workspace.id);
  const remove = useRemoveBrandImage(workspace.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const images = workspace.brand_profile.brand_images ?? [];

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(null);
    try {
      await add.mutateAsync(file);
    } catch {
      setError("Couldn’t add that image. Use a JPG, PNG, or WebP under 8 MB.");
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Brand images · {images.length} of {MAX_BRAND_IMAGES}
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
          disabled={!canAddBrandImage(images.length, isDemo)}
          title={isDemo ? "Disabled in the demo" : undefined}
        >
          <Upload className="h-4 w-4" aria-hidden />
          Add image
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Save your own images here to reuse them as card pictures — pick them from the image picker
        when generating a card.
      </p>
      {error && <span className="text-xs text-destructive">{error}</span>}
      {images.length === 0 ? (
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          <ImageOff className="h-4 w-4" aria-hidden />
          No brand images yet.
        </span>
      ) : (
        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4">
          {images.map((img) => (
            <ImageTile
              key={img.id}
              image={img}
              isDemo={isDemo}
              removing={remove.isPending}
              onRemove={() => remove.mutate(img.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ImageTile({
  image,
  isDemo,
  removing,
  onRemove,
}: {
  image: BrandImage;
  isDemo: boolean;
  removing: boolean;
  onRemove: () => void;
}) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    if (!image.url) return;
    fetchImageDataUrl(image.url)
      .then((d) => alive && setDataUrl(d))
      .catch(() => alive && setDataUrl(null));
    return () => {
      alive = false;
    };
  }, [image.url]);

  return (
    <li className="group relative aspect-square overflow-hidden rounded-md border border-border bg-surface-variant">
      {dataUrl ? (
        <img src={dataUrl} alt={image.name ?? ""} className="h-full w-full object-cover" />
      ) : (
        <span className="absolute inset-0 animate-pulse bg-muted-foreground/10" aria-hidden />
      )}
      {!isDemo && (
        <Button
          type="button"
          size="icon"
          variant="secondary"
          onClick={onRemove}
          loading={removing}
          aria-label={`Remove ${image.name ?? "image"}`}
          className="absolute right-1 top-1 h-7 w-7 opacity-0 shadow-medium transition-opacity focus-visible:opacity-100 group-hover:opacity-100 hover:text-destructive"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden />
        </Button>
      )}
    </li>
  );
}
