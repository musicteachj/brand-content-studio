import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Workspace } from "@/types";
import { LogoPreview } from "./LogoPreview";

export function BrandIdentityView({
  workspace,
  canEdit,
  onEdit,
}: {
  workspace: Workspace;
  canEdit: boolean;
  onEdit: () => void;
}) {
  const brand = workspace.brand_profile;
  const fonts = [
    ["Heading", brand.fonts.heading],
    ["Body", brand.fonts.body],
    ["Mono", brand.fonts.mono],
  ].filter(([, v]) => v) as [string, string][];

  return (
    <div className="flex flex-col gap-5 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex items-start justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Colors
        </span>
        {canEdit && (
          <Button size="sm" variant="secondary" onClick={onEdit}>
            <Pencil className="h-4 w-4" aria-hidden />
            Edit
          </Button>
        )}
      </div>
      <div className="flex flex-wrap gap-3">
        {brand.colors.map((c) => (
          <div key={`${c.hex}-${c.name}`} className="flex items-center gap-2">
            <span
              className="h-7 w-7 rounded-md border border-border"
              style={{ backgroundColor: c.hex }}
              aria-hidden
            />
            <div className="flex flex-col leading-tight">
              <span className="text-xs font-medium text-foreground">{c.name}</span>
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                {c.hex}
                {brand.accent_hex?.toLowerCase() === c.hex.toLowerCase() ? " · accent" : ""}
              </span>
            </div>
          </div>
        ))}
        {brand.colors.length === 0 && (
          <span className="text-sm text-muted-foreground">No colors yet.</span>
        )}
      </div>

      {fonts.length > 0 && (
        <div className="flex flex-col gap-2.5 border-t border-border pt-4">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Typography
          </span>
          <dl className="flex flex-col gap-1.5">
            {fonts.map(([role, name]) => (
              <div key={role} className="flex items-baseline justify-between gap-4">
                <dt className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                  {role}
                </dt>
                <dd className="text-sm text-foreground">{name}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {brand.voice_summary && (
        <div className="flex flex-col gap-2 border-t border-border pt-4">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Voice
          </span>
          <p className="text-sm leading-relaxed text-foreground">{brand.voice_summary}</p>
        </div>
      )}

      <div className="flex flex-col gap-2.5 border-t border-border pt-4">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Logo
        </span>
        <LogoPreview url={brand.logo?.url ?? null} />
      </div>
    </div>
  );
}
