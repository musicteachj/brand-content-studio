import { useEffect } from "react";
import { injectFontFace } from "@/styles/brandFonts";
import type { UploadedFont } from "@/types";

export function FontPreview({
  family,
  uploaded = [],
}: {
  family: string | null | undefined;
  uploaded?: UploadedFont[];
}) {
  useEffect(() => {
    if (family) injectFontFace(family, uploaded);
  }, [family, uploaded]);
  if (!family) return null;
  return (
    <p
      className="mt-1.5 truncate text-sm text-muted-foreground"
      style={{ fontFamily: `"${family}", serif` }}
    >
      The quick brown fox
    </p>
  );
}
