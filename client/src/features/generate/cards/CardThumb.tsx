import { buildCardElement } from "@/features/generate/cards/cardElement";
import { ScaledCardBox } from "@/features/generate/cards/ScaledCardBox";
import type { BrandProfile, CardOutput } from "@/types";

/** A history thumbnail of a card generation — the same archetype element used in
 *  the preview/export, scaled down. Unsplash images render from their remote URL
 *  directly; uploaded images are auth-gated so they're omitted from the thumbnail
 *  (the brand-color field + copy still render). Inject the workspace fonts once at
 *  the page level (injectBrandFontFaces) so the type matches the export. */
export function CardThumb({ output, brand }: { output: CardOutput; brand: BrandProfile }) {
  const imageSrc = output.image?.source === "unsplash" ? output.image.url : null;
  return (
    <ScaledCardBox>
      {buildCardElement({
        template: output.template_id,
        fields: output.fields,
        brand,
        imageSrc,
        attribution: output.image?.attribution ?? null,
      })}
    </ScaledCardBox>
  );
}
