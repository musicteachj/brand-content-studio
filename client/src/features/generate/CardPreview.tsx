import { useEffect, useState } from "react";
import { Check, Download, ImageIcon, ImageMinus, ImagePlus, Pencil } from "lucide-react";
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
import { StreamAnnouncer } from "@/features/generate/StreamAnnouncer";
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
  accentHex: string | null;
  imageDataUrl: string | null;
  attribution: ImageAttribution | null;
  error: string | null;
  hasImage: boolean;
  imageError: string | null;
  onAddImage: () => void;
  onClearImage?: () => void; // un-pick the current image (ARCH-04)
  // Inline text editing (Phase 1.5). When `onEditField` is provided the card can
  // enter an in-place edit mode; `editKey` re-seeds the editable fields when the
  // generation/template changes.
  editingText?: boolean;
  onToggleEditText?: () => void;
  onEditField?: (key: keyof CardFields, value: string) => void;
  editKey?: string;
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
  accentHex,
  imageDataUrl,
  attribution,
  error,
  hasImage,
  imageError,
  onAddImage,
  onClearImage,
  editingText = false,
  onToggleEditText,
  onEditField,
  editKey,
}: Props) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const usesImage = templateUsesImage(template);
  // Add-image is offered while streaming (parallel) and after; export only once done.
  const showAddImage = usesImage && (status === "streaming" || status === "done");
  const showExport = status === "done";
  const canEditText = status === "done" && !!onEditField && !!onToggleEditText;

  // Load the workspace fonts into the DOM so the live/fallback render matches the
  // Satori export (which loads the same TTFs as buffers).
  useEffect(() => {
    injectBrandFontFaces(brand.fonts, brand.uploaded_fonts ?? []);
  }, [brand.fonts, brand.uploaded_fonts]);

  const elementProps: CardElementProps = {
    template,
    fields: fields ?? { eyebrow: "", headline: "", body: "", cta: "", hashtag: "" },
    brand,
    accentHex,
    imageSrc: imageDataUrl,
    attribution,
  };

  // Render the locked Satori SVG once the copy is finalized — this is what the
  // PNG export rasterizes, so what you see is what you export. Paused while
  // editing text (the editable DOM card is shown instead), so Satori doesn't
  // re-rasterize on every keystroke.
  const lockedReady = status === "done" && fields !== null && !editingText;
  const { svg, loading: svgLoading } = useCardSvg(lockedReady, elementProps);
  const showEditableCard = status === "done" && fields !== null && editingText && !!onEditField;

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
      <StreamAnnouncer status={status} label="Card" />
      <div className="rounded-xl bg-preview-bg p-5 sm:p-7">
        <div
          className="mx-auto w-full max-w-[400px] overflow-hidden rounded-xl shadow-preview"
          aria-busy={status === "streaming"}
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
          {showEditableCard ? (
            // In-place editing: the real DOM card with contentEditable fields.
            // `editKey` re-seeds the fields when the generation/template changes.
            <ScaledCardBox key={editKey}>
              {buildCardElement({ ...elementProps, edit: { onEdit: onEditField! } })}
            </ScaledCardBox>
          ) : lockedReady && svg ? (
            <img src={svgToDataUrl(svg)} alt="Card preview" className="block w-full" />
          ) : lockedReady ? (
            // Satori still rendering (or font load) — show the DOM card meanwhile.
            <ScaledCardBox>{buildCardElement(elementProps)}</ScaledCardBox>
          ) : null}
        </div>
      </div>

      {/* Finishing actions at the base of the card: add/swap the image (photo-led),
          edit the copy in place, and export. Image is available while copy streams
          (parallel step); edit + export appear once the card is locked. While
          editing, a single "Done" action replaces the row and the export pauses. */}
      {editingText ? (
        <div className="flex flex-col gap-2">
          <Button onClick={onToggleEditText}>
            <Check className="h-4 w-4" aria-hidden />
            Done editing
          </Button>
          <p className="text-center text-[11px] text-muted-foreground">
            Click any field on the card to edit it. Changes save when you press “Save changes”.
          </p>
        </div>
      ) : (
        (showAddImage || showExport) && (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              {showAddImage && (
                <Button
                  variant="secondary"
                  onClick={onAddImage}
                  className={cn(
                    "min-w-[120px] flex-1",
                    // Nudge the image as the next step once the card is ready but bare.
                    // Accent-outlined nudge. Border + hover carry the accent; the
                    // label stays --foreground so it passes AA in both themes
                    // (text-accent on the dark surface was only 3.73:1).
                    status === "done" && !hasImage && "border-accent hover:bg-accent/5",
                  )}
                >
                  <ImagePlus className="h-4 w-4" aria-hidden />
                  {hasImage ? "Change image" : "Add an image"}
                </Button>
              )}
              {showAddImage && hasImage && onClearImage && (
                <Button variant="ghost" onClick={onClearImage} aria-label="Remove image">
                  <ImageMinus className="h-4 w-4" aria-hidden />
                  Remove
                </Button>
              )}
              {canEditText && (
                <Button
                  variant="secondary"
                  onClick={onToggleEditText}
                  className="min-w-[120px] flex-1"
                >
                  <Pencil className="h-4 w-4" aria-hidden />
                  Edit text
                </Button>
              )}
              {showExport && (
                <Button
                  onClick={onExport}
                  disabled={!svg || exporting}
                  loading={exporting}
                  className="min-w-[120px] flex-1"
                >
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
        )
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
