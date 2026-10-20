import { useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Check, ImageOff, Search, Upload, X } from "lucide-react";
import { fetchImageDataUrl, uploadImage, useUnsplashSearch } from "@/api/images";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiErrorMessage } from "@/lib/apiError";
import { cn } from "@/lib/utils";
import type { BrandImage, UnsplashPhoto } from "@/types";

interface Props {
  open: boolean;
  onClose: () => void;
  workspaceId: string | null;
  initialKeywords: string[];
  selectedKey: string | null; // unsplash id or upload storage_key
  brandImages: BrandImage[]; // the workspace's reusable brand-image library
  onSelectUnsplash: (photo: UnsplashPhoto) => void;
  onSelectUpload: (url: string, storageKey: string) => void;
  onSaveBrandImage?: (file: File) => Promise<void>;
}

export function ImagePickerPanel({
  open,
  onClose,
  workspaceId,
  initialKeywords,
  selectedKey,
  brandImages,
  onSelectUnsplash,
  onSelectUpload,
  onSaveBrandImage,
}: Props) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [lastUpload, setLastUpload] = useState<File | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const seededRef = useRef(false);

  // The panel can be opened before the card is generated (image selection is a
  // parallel step), so the search starts empty and is auto-seeded from the model's
  // keywords once they arrive, whether that's before opening or while open. Seed
  // at most once, and never clobber a query the user has already typed.
  useEffect(() => {
    if (!open) {
      seededRef.current = false;
      return;
    }
    if (seededRef.current || input.trim() !== "" || initialKeywords.length === 0) return;
    const seed = initialKeywords.slice(0, 2).join(" ");
    seededRef.current = true;
    setInput(seed);
    setQuery(seed);
  }, [open, initialKeywords, input]);

  const search = useUnsplashSearch(query);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !workspaceId) return;
    setUploading(true);
    setUploadError(null);
    try {
      const res = await uploadImage(workspaceId, file);
      onSelectUpload(res.url, res.storage_key);
      setLastUpload(file);
      setSaved(false);
    } catch (err) {
      setUploadError(apiErrorMessage(err, "Upload failed. Use a JPG, PNG, or WebP under 8 MB."));
    } finally {
      setUploading(false);
    }
  }

  async function saveToBrandImages() {
    if (!onSaveBrandImage || !lastUpload) return;
    setSaving(true);
    setUploadError(null);
    try {
      await onSaveBrandImage(lastUpload);
      setSaved(true);
    } catch (err) {
      setUploadError(
        apiErrorMessage(err, "Couldn’t save to brand images (the 24-image limit may be reached)."),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-picker animate-fade-in bg-foreground/20" />
        <Dialog.Content
          className="fixed right-0 top-0 z-picker flex h-full w-full max-w-md animate-slide-in-right flex-col border-l border-border bg-surface shadow-heavy"
          aria-describedby={undefined}
        >
          <header className="flex items-center justify-between border-b border-border px-5 py-4">
            <Dialog.Title className="text-sm font-semibold text-foreground">
              Choose an image
            </Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-surface-variant hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X className="h-4 w-4" aria-hidden />
            </Dialog.Close>
          </header>

          <div className="border-b border-border px-5 py-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setQuery(input);
              }}
              className="flex gap-2"
            >
              <div className="relative flex-1">
                <Search
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden
                />
                <Input
                  aria-label="Search Unsplash"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Search photos…"
                  className="pl-9"
                />
              </div>
              <Button type="submit" variant="secondary" size="sm">
                Search
              </Button>
            </form>
            <div className="mt-3 flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">Photos via Unsplash</p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => fileRef.current?.click()}
                loading={uploading}
                disabled={!workspaceId}
              >
                <Upload className="h-4 w-4" aria-hidden />
                Upload
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={onUpload}
              />
              {onSaveBrandImage && lastUpload && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={saveToBrandImages}
                  loading={saving}
                  disabled={saved}
                  aria-label="Save to brand images"
                >
                  {saved ? "Saved ✓" : "Save to brand images"}
                </Button>
              )}
            </div>
            {uploadError && (
              <p role="alert" className="mt-2 text-xs text-destructive">
                {uploadError}
              </p>
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {brandImages.length > 0 && (
              <section className="mb-5">
                <p className="mb-2 eyebrow">Brand images</p>
                <div className="grid grid-cols-3 gap-3">
                  {brandImages.map((img) => (
                    <BrandImageTile
                      key={img.id}
                      image={img}
                      selected={selectedKey === img.storage_key}
                      onSelect={() => onSelectUpload(img.url ?? "", img.storage_key)}
                    />
                  ))}
                </div>
              </section>
            )}
            {!query && (
              <p className="py-10 text-center text-sm text-muted-foreground">
                Search for a photo, or upload your own.
              </p>
            )}
            {query && search.isLoading && <Skeleton />}
            {query && search.isError && (
              <div className="flex flex-col items-center py-10 text-center">
                <ImageOff className="h-6 w-6 text-muted-foreground" aria-hidden />
                <p className="mt-3 text-sm text-destructive">
                  Couldn’t reach Unsplash. Check the server’s UNSPLASH_ACCESS_KEY.
                </p>
              </div>
            )}
            {query && search.data && search.data.results.length === 0 && (
              <p className="py-10 text-center text-sm text-muted-foreground">
                No photos for “{query}”.
              </p>
            )}
            {query && search.data && search.data.results.length > 0 && (
              <div className="columns-2 gap-3 *:mb-3">
                {search.data.results.map((photo) => (
                  <PhotoTile
                    key={photo.id}
                    photo={photo}
                    selected={selectedKey === photo.id}
                    onSelect={() => onSelectUnsplash(photo)}
                  />
                ))}
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PhotoTile({
  photo,
  selected,
  onSelect,
}: {
  photo: UnsplashPhoto;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <div className="break-inside-avoid">
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "relative block w-full overflow-hidden rounded-lg border focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
          selected
            ? "border-accent ring-2 ring-accent"
            : "border-border hover:border-muted-foreground",
        )}
        style={{ aspectRatio: `${photo.width} / ${photo.height}` }}
      >
        <img
          src={photo.thumb_url}
          alt={photo.description ?? "Unsplash photo"}
          loading="lazy"
          className="h-full w-full object-cover"
          style={{ backgroundColor: photo.color ?? "hsl(var(--surface-variant))" }}
        />
        {selected && (
          <span className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-accent text-accent-foreground">
            <Check className="h-3.5 w-3.5" aria-hidden />
          </span>
        )}
      </button>
      {/* Attribution is rendered visibly (never a tooltip), per the Unsplash license. */}
      <p className="mt-1 truncate text-[11px] leading-tight text-muted-foreground">
        Photo by{" "}
        <a
          href={photo.attribution.author_url}
          target="_blank"
          rel="noreferrer"
          className="underline decoration-border underline-offset-2 hover:text-foreground"
          onClick={(e) => e.stopPropagation()}
        >
          {photo.attribution.author}
        </a>{" "}
        on Unsplash
      </p>
    </div>
  );
}

function BrandImageTile({
  image,
  selected,
  onSelect,
}: {
  image: BrandImage;
  selected: boolean;
  onSelect: () => void;
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
    <button
      type="button"
      onClick={onSelect}
      aria-label={`Use ${image.name ?? "brand image"}`}
      className={cn(
        "relative block aspect-square w-full overflow-hidden rounded-lg border bg-surface-variant focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
        selected
          ? "border-accent ring-2 ring-accent"
          : "border-border hover:border-muted-foreground",
      )}
    >
      {dataUrl ? (
        <img src={dataUrl} alt="" className="h-full w-full object-cover" />
      ) : (
        <span className="absolute inset-0 animate-pulse bg-muted-foreground/10" aria-hidden />
      )}
      {selected && (
        <span className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-accent text-accent-foreground">
          <Check className="h-3.5 w-3.5" aria-hidden />
        </span>
      )}
    </button>
  );
}

function Skeleton() {
  return (
    <div className="columns-2 gap-3 *:mb-3">
      {[3 / 4, 4 / 5, 5 / 6, 3 / 4, 4 / 5, 5 / 6].map((ar, i) => (
        <div
          key={i}
          className="animate-pulse rounded-lg bg-surface-variant"
          style={{ aspectRatio: `${ar}` }}
        />
      ))}
    </div>
  );
}
