import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { fetchImageDataUrl } from "@/api/images";

export function LogoPreview({ url }: { url: string | null }) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setDataUrl(null);
    if (!url) return;
    fetchImageDataUrl(url)
      .then((d) => alive && setDataUrl(d))
      .catch(() => alive && setDataUrl(null));
    return () => {
      alive = false;
    };
  }, [url]);

  if (!url) {
    return (
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        <ImageOff className="h-4 w-4" aria-hidden />
        No logo uploaded.
      </span>
    );
  }
  return (
    <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-md border border-border bg-surface-variant">
      {dataUrl ? (
        <img src={dataUrl} alt="Brand logo" className="max-h-full max-w-full object-contain" />
      ) : (
        <span className="h-4 w-4 animate-pulse rounded bg-muted-foreground/30" aria-hidden />
      )}
    </div>
  );
}
