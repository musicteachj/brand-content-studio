import { cardColors } from "@/features/generate/cards/cardElement";
import { cn } from "@/lib/utils";
import type { BrandProfile, CardTemplate } from "@/types";

const TEMPLATES: { id: CardTemplate; label: string }[] = [
  { id: "photo-led", label: "Photo-led" },
  { id: "statement", label: "Statement" },
  { id: "quote", label: "Quote" },
];

interface Props {
  brand: BrandProfile;
  value: CardTemplate | null;
  onChange: (t: CardTemplate) => void;
  disabled?: boolean;
}

/** Horizontal row of layout thumbnails (DESIGN §4). Selected = 2px accent border.
 *  Never auto-selects — the user must pick before generating. The mini previews
 *  use the workspace's own colors so the picker reflects the brand. */
export function TemplatePicker({ brand, value, onChange, disabled }: Props) {
  return (
    <div className="grid grid-cols-3 gap-2.5" role="radiogroup" aria-label="Card template">
      {TEMPLATES.map((t) => {
        const selected = value === t.id;
        return (
          <button
            key={t.id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(t.id)}
            className={cn(
              "flex flex-col gap-1.5 rounded-lg border p-1.5 text-left transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
              selected
                ? "border-2 border-accent shadow-light"
                : "border border-border hover:shadow-light",
            )}
          >
            <Thumb template={t.id} brand={brand} />
            <span className="px-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
              {t.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function Thumb({ template, brand }: { template: CardTemplate; brand: BrandProfile }) {
  const c = cardColors(brand);
  const line = (w: string, color: string, h = 4) => (
    <div style={{ width: w, height: h, backgroundColor: color, borderRadius: 1 }} />
  );

  if (template === "photo-led") {
    return (
      <div
        className="relative aspect-[4/5] w-full overflow-hidden rounded"
        style={{ backgroundColor: c.ink }}
      >
        <div
          className="absolute inset-x-0 bottom-0 flex flex-col gap-1 p-1.5"
          style={{ background: `linear-gradient(180deg, transparent, ${c.ink})` }}
        >
          {line("40%", c.accent, 3)}
          {line("85%", c.paper, 6)}
          {line("60%", c.paper, 3)}
        </div>
      </div>
    );
  }
  if (template === "statement") {
    return (
      <div
        className="flex aspect-[4/5] w-full flex-col justify-center gap-1.5 rounded p-1.5"
        style={{ backgroundColor: c.ink }}
      >
        {line("28%", c.accent, 3)}
        {line("90%", c.paper, 7)}
        {line("70%", c.paper, 7)}
        {line("50%", c.paper, 3)}
      </div>
    );
  }
  return (
    <div
      className="flex aspect-[4/5] w-full flex-col justify-center gap-1.5 rounded p-1.5"
      style={{ backgroundColor: c.paper }}
    >
      <span
        style={{ color: c.accent, fontSize: 22, lineHeight: 0.6, fontFamily: "Georgia, serif" }}
      >
        &ldquo;
      </span>
      {line("85%", c.ink, 5)}
      {line("65%", c.ink, 5)}
    </div>
  );
}
