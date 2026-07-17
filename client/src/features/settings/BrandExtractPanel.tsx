import { useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { useExtractBrand } from "@/api/workspaces";
import { Button } from "@/components/ui/button";
import type { BrandExtract } from "@/types";

/** "Learn from an image" (Phase 4c): upload a logo/guideline page → Claude vision
 *  proposes a palette + voice + fonts. Proposal only — `onApply` hands it to the
 *  form for review; nothing persists until the form is saved. */
export function BrandExtractPanel({
  workspaceId,
  onApply,
}: {
  workspaceId: string;
  onApply: (proposal: BrandExtract) => void;
}) {
  const extract = useExtractBrand(workspaceId);
  const extractRef = useRef<HTMLInputElement>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<BrandExtract | null>(null);

  async function onExtractFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setExtractError(null);
    setProposal(null);
    try {
      setProposal(await extract.mutateAsync(file));
    } catch {
      setExtractError("Couldn’t read that image. Use a JPG, PNG, or WebP under 8 MB.");
    }
  }

  function apply() {
    if (!proposal) return;
    onApply(proposal);
    setProposal(null);
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-dashed border-border bg-surface-variant/40 p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col">
          <span className="text-sm font-medium text-foreground">Learn from an image</span>
          <span className="text-xs text-muted-foreground">
            Upload a logo or guideline page — we’ll propose a palette, voice, and fonts to review.
          </span>
        </div>
        <input
          ref={extractRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={onExtractFile}
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => extractRef.current?.click()}
          loading={extract.isPending}
        >
          <Sparkles className="h-4 w-4" aria-hidden />
          Extract from image
        </Button>
      </div>
      {extractError && (
        <span role="alert" className="text-xs text-destructive">
          {extractError}
        </span>
      )}
      {proposal && (
        <div className="mt-1 flex flex-col gap-3 rounded-md border border-border bg-surface p-3">
          <span className="eyebrow">Proposed — review before applying</span>
          <div className="flex flex-wrap gap-2">
            {proposal.colors.map((c) => (
              <span key={`${c.hex}-${c.name}`} className="flex items-center gap-1.5">
                <span
                  className="h-5 w-5 rounded border border-border"
                  style={{ backgroundColor: c.hex }}
                  aria-hidden
                />
                <span className="eyebrow">{c.hex}</span>
              </span>
            ))}
          </div>
          {proposal.voice_summary && (
            <p className="text-xs leading-relaxed text-muted-foreground">
              <span className="font-medium text-foreground">Voice: </span>
              {proposal.voice_summary}
            </p>
          )}
          {(proposal.fonts.heading || proposal.fonts.body || proposal.fonts.mono) && (
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Fonts: </span>
              {[proposal.fonts.heading, proposal.fonts.body, proposal.fonts.mono]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
          <div className="flex items-center gap-2">
            <Button type="button" size="sm" onClick={apply}>
              Apply to form
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setProposal(null)}>
              Dismiss
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Applying fills the fields below — review, then <strong>Save changes</strong> to persist.
          </p>
        </div>
      )}
    </div>
  );
}
