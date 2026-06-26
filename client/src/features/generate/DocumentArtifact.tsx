// Renders a generated document in the right shape for its archetype: a one-pager
// is "paper" (DocumentPage), a short-deck is a slide stack (DeckPreview). Shared
// by the Generate preview, History thumbnails (compact), and the detail dialog,
// so every surface renders an archetype the same way.
import { DeckPreview } from "./DeckPreview";
import { DocumentPage } from "./DocumentPage";
import type { BrandProfile, DocumentModel } from "@/types";

interface Props {
  document: DocumentModel;
  brand: BrandProfile;
  compact?: boolean;
  className?: string;
}

export function DocumentArtifact({ document: doc, brand, compact, className }: Props) {
  if (doc.archetype === "short-deck") {
    return <DeckPreview document={doc} brand={brand} compact={compact} className={className} />;
  }
  return <DocumentPage document={doc} brand={brand} compact={compact} className={className} />;
}
