import { useEffect, useRef, useState, type RefObject } from "react";
import { ImageOff, Trash2, Upload } from "lucide-react";
import { fetchImageDataUrl } from "@/api/images";
import { useAddBrandImage, useRemoveBrandImage, useRenameBrandImage } from "@/api/workspaces";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { apiErrorMessage } from "@/lib/apiError";
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
  const rename = useRenameBrandImage(workspace.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const countRef = useRef<HTMLSpanElement>(null);
  const [error, setError] = useState<string | null>(null);
  const images = workspace.brand_profile.brand_images ?? [];

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(null);
    try {
      await add.mutateAsync(file);
    } catch (err) {
      setError(
        apiErrorMessage(err, "Couldn’t add that image. Use a JPG, PNG, or WebP under 8 MB."),
      );
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span ref={countRef} tabIndex={-1} className="eyebrow focus-visible:outline-hidden">
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
        Save your own images here to reuse them as card pictures. Pick them from the image picker
        when generating a card.
      </p>
      {error && (
        <span role="alert" className="text-xs text-destructive">
          {error}
        </span>
      )}
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
              onRemove={async () => {
                await remove.mutateAsync(img.id);
              }}
              focusAfterRemove={countRef}
              onRename={(name) => rename.mutate({ imageId: img.id, name })}
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
  onRemove,
  focusAfterRemove,
  onRename,
}: {
  image: BrandImage;
  isDemo: boolean;
  onRemove: () => Promise<void>;
  focusAfterRemove: RefObject<HTMLElement | null>;
  onRename: (name: string) => void;
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
    <li className="flex flex-col gap-1">
      <div className="group relative aspect-square overflow-hidden rounded-md border border-border bg-surface-variant">
        {dataUrl ? (
          <img src={dataUrl} alt={image.name ?? ""} className="h-full w-full object-cover" />
        ) : (
          <span className="absolute inset-0 animate-pulse bg-muted-foreground/10" aria-hidden />
        )}
        {!isDemo && (
          <ConfirmDialog
            trigger={
              <Button
                type="button"
                size="icon"
                variant="secondary"
                aria-label={`Remove ${image.name ?? "image"}`}
                className="absolute right-1 top-1 h-7 w-7 opacity-0 shadow-medium transition-opacity focus-visible:opacity-100 group-hover:opacity-100 pointer-coarse:opacity-100 hover:text-destructive"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden />
              </Button>
            }
            title={image.name ? `Remove “${image.name}”?` : "Remove this image?"}
            description="This removes it from your brand images. Cards that already use it keep their picture. This can’t be undone."
            confirmLabel="Remove image"
            onConfirm={onRemove}
            errorFallback="Couldn’t remove this image. Try again."
            focusAfterConfirm={focusAfterRemove}
          />
        )}
      </div>
      {isDemo ? (
        <span className="truncate text-[11px] text-muted-foreground">{image.name}</span>
      ) : (
        <input
          defaultValue={image.name ?? ""}
          aria-label="Rename image"
          onBlur={(e) => {
            const v = e.target.value.trim();
            if (v && v !== image.name) onRename(v);
          }}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          className="w-full rounded-sm border border-transparent bg-transparent px-1 text-[11px] text-muted-foreground hover:border-border focus:border-border focus:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        />
      )}
    </li>
  );
}
