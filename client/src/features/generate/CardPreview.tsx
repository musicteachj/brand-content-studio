import { useEffect, useState } from "react";
import { Download, ImageIcon, ImagePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  buildCardElement,
  CARD_H,
  CARD_W,
  cardColors,
  templateUsesImage,
  type CardElementProps,
} from "@/features/generate/cards/cardElement";
import { ScaledCardBox } from "@/features/generate/cards/ScaledCardBox";
import {
  cardPngName,
  downloadBlob,
  svgToDataUrl,
  svgToPng,
  useCardSvg,
} from "@/features/generate/useCardExport";
import { bodyFamily, headingFamily, injectBrandFontFaces } from "@/styles/brandFonts";
import { cn } from "@/lib/utils";
import type { BrandProfile, CardFields, CardTemplate, ImageAttribution } from "@/types";

interface Props {
  status: "idle" | "streaming" | "done" | "error";
  copy: string;
  template: CardTemplate;
  fields: CardFields | null;
  brand: BrandProfile;
  imageDataUrl: string | null;
  attribution: ImageAttribution | null;
  error: string | null;
  hasImage: boolean;
  imageError: string | null;
  onAddImage: () => void;
}

function DraftingCard({
  copy,
  template,
  brand,
}: {
  copy: string;
  template: CardTemplate;
  brand: BrandProfile;
}) {
  const c = cardColors(brand);
  const onLight = template === "quote";
  const bg = onLight ? c.paper : c.ink;
  const fg = onLight ? c.ink : c.paper;
  return (
    <div
      style={{
        width: CARD_W,
        height: CARD_H,
        backgroundColor: bg,
        padding: 88,
        display: "flex",
        flexDirection: "column",
        fontFamily: bodyFamily(brand.fonts),
      }}
    >
      <div
        style={{
          fontFamily: bodyFamily(brand.fonts),
          fontSize: 25,
          fontWeight: 600,
          letterSpacing: 5,
          textTransform: "uppercase",
          color: c.accent,
          marginBottom: 40,
        }}
      >
        Writing…
      </div>
      <div
        style={{
          fontFamily: headingFamily(brand.fonts),
          fontSize: 46,
          lineHeight: 1.25,
          color: fg,
          whiteSpace: "pre-wrap",
        }}
      >
        {copy}
        <span style={{ color: c.accent }}>▌</span>
      </div>
    </div>
  );
}

export function CardPreview({
  status,
  copy,
  template,
  fields,
  brand,
  imageDataUrl,
  attribution,
  error,
  hasImage,
  imageError,
  onAddImage,
}: Props) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const usesImage = templateUsesImage(template);
  // Add-image is offered while streaming (parallel) and after; export only once done.
  const showAddImage = usesImage && (status === "streaming" || status === "done");
  const showExport = status === "done";

  // Load the workspace fonts into the DOM so the live/fallback render matches the
  // Satori export (which loads the same TTFs as buffers).
  useEffect(() => {
    injectBrandFontFaces(brand.fonts);
  }, [brand.fonts]);

  const elementProps: CardElementProps = {
    template,
    fields: fields ?? { eyebrow: "", headline: "", body: "", cta: "", hashtag: "" },
    brand,
    imageSrc: imageDataUrl,
    attribution,
  };

  // Render the locked Satori SVG once the copy is finalized — this is what the
  // PNG export rasterizes, so what you see is what you export.
  const ready = status === "done" && fields !== null;
  const { svg, loading: svgLoading } = useCardSvg(ready, elementProps);

  async function onExport() {
    if (!svg) return;
    setExporting(true);
    setExportError(null);
    try {
      const png = await svgToPng(svg);
      downloadBlob(png, cardPngName(fields?.headline ?? ""));
    } catch (err) {
      setExportError((err as Error).message);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl bg-preview-bg p-5 sm:p-7">
        <div
          className="mx-auto w-full max-w-[400px] overflow-hidden rounded-xl shadow-preview"
          aria-live="polite"
        >
          {status === "idle" && <IdlePlaceholder />}
          {status === "error" && (
            <div className="flex aspect-[4/5] items-center justify-center bg-surface p-8 text-center">
              <p role="alert" className="text-sm text-destructive">
                {error ?? "Generation failed."}
              </p>
            </div>
          )}
          {status === "streaming" && (
            <ScaledCardBox>
              <DraftingCard copy={copy} template={template} brand={brand} />
            </ScaledCardBox>
          )}
          {ready && svg ? (
            <img src={svgToDataUrl(svg)} alt="Card preview" className="block w-full" />
          ) : ready ? (
            // Satori still rendering (or font load) — show the DOM card meanwhile.
            <ScaledCardBox>{buildCardElement(elementProps)}</ScaledCardBox>
          ) : null}
        </div>
      </div>

      {/* Finishing actions, in one compact row at the base of the card: add/swap the
          image (photo-led) and export. The image button is available while the copy
          still streams (image selection is a parallel step); export appears once the
          card is locked. Kept on one line so both stay in view under the card. */}
      {(showAddImage || showExport) && (
        <div className="flex flex-col gap-2">
          <div
            className={cn("grid gap-2", showAddImage && showExport ? "grid-cols-2" : "grid-cols-1")}
          >
            {showAddImage && (
              <Button
                variant="secondary"
                onClick={onAddImage}
                className={cn(
                  // Nudge the image as the next step once the card is ready but bare.
                  status === "done" && !hasImage && "border-accent text-accent hover:bg-accent/5",
                )}
              >
                <ImagePlus className="h-4 w-4" aria-hidden />
                {hasImage ? "Change image" : "Add an image"}
              </Button>
            )}
            {showExport && (
              <Button onClick={onExport} disabled={!svg || exporting} loading={exporting}>
                <Download className="h-4 w-4" aria-hidden />
                {svgLoading && !svg ? "Preparing…" : "Export PNG"}
              </Button>
            )}
          </div>
          {showExport && (
            <p className="text-center text-[11px] text-muted-foreground">
              Exports a crisp 1080×1350 PNG
            </p>
          )}
          {imageError && (
            <p role="alert" className="text-xs text-destructive">
              {imageError}
            </p>
          )}
          {exportError && (
            <p role="alert" className="text-xs text-destructive">
              {exportError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function IdlePlaceholder() {
  return (
    <div className="flex aspect-[4/5] flex-col items-center justify-center bg-surface p-8 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-surface-variant text-muted-foreground">
        <ImageIcon className="h-5 w-5" aria-hidden />
      </span>
      <p className="mt-4 text-sm font-medium text-foreground">Your card will appear here</p>
      <p className="mt-1 max-w-xs text-sm text-muted-foreground">
        Pick a template and generate — copy streams in live, in your brand’s type and color.
      </p>
    </div>
  );
}
