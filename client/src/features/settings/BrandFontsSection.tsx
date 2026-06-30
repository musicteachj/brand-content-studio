import { useRef, useState } from "react";
import { Trash2, Type, Upload } from "lucide-react";
import { useAddFont, useRemoveFont } from "@/api/workspaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/auth";
import type { Workspace } from "@/types";

const MAX_FONTS = 8;

/** Settings → Brand fonts. Upload your own .ttf fonts; they appear in the font
 *  picker and render on cards + embed in PDFs. Demo-blocked; capped. */
export function BrandFontsSection({ workspace }: { workspace: Workspace }) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const add = useAddFont(workspace.id);
  const remove = useRemoveFont(workspace.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fonts = workspace.brand_profile.uploaded_fonts ?? [];

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!name.trim()) {
      setError("Give the font a name first (e.g. its family name).");
      return;
    }
    setError(null);
    try {
      await add.mutateAsync({ file, name: name.trim() });
      setName("");
    } catch {
      setError("Couldn’t add that font. Upload a .ttf under 5 MB with a unique name.");
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Brand fonts · {fonts.length} of {MAX_FONTS}
        </span>
        <div className="flex items-center gap-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Font name (e.g. Acme Sans)"
            className="h-8 w-44 text-sm"
            disabled={isDemo}
          />
          <input ref={fileRef} type="file" accept=".ttf" className="hidden" onChange={onFile} />
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => fileRef.current?.click()}
            loading={add.isPending}
            disabled={isDemo || fonts.length >= MAX_FONTS}
            title={isDemo ? "Disabled in the demo" : undefined}
          >
            <Upload className="h-4 w-4" aria-hidden />
            Add .ttf
          </Button>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        Upload your own TrueType fonts — they appear in the font picker and render on cards and in
        exported PDFs.
      </p>
      {error && <span className="text-xs text-destructive">{error}</span>}
      {fonts.length === 0 ? (
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          <Type className="h-4 w-4" aria-hidden />
          No uploaded fonts yet.
        </span>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {fonts.map((f) => (
            <li
              key={f.id}
              className="flex items-center justify-between rounded-md border border-border px-3 py-2"
            >
              <span
                className="text-sm text-foreground"
                style={{ fontFamily: `"${f.family}", serif` }}
              >
                {f.family}
              </span>
              {!isDemo && (
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  onClick={() => remove.mutate(f.id)}
                  loading={remove.isPending}
                  aria-label={`Remove ${f.family}`}
                  className="h-7 w-7 hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
