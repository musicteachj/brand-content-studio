import { useEffect, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { ImageOff, Pencil, Plus, Sparkles, Trash2, Upload, X } from "lucide-react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { fetchImageDataUrl } from "@/api/images";
import { injectFontFace } from "@/styles/brandFonts";
import { optionsForRole } from "@/styles/fontCatalog";
import {
  useDeleteLogo,
  useExtractBrand,
  useUpdateWorkspace,
  useUploadLogo,
} from "@/api/workspaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore } from "@/stores/auth";
import type { BrandExtract, UploadedFont, Workspace } from "@/types";
import {
  brandSchema,
  buildBrandProfile,
  HEX_RE,
  proposalToForm,
  ROLES,
  toForm,
  type BrandForm,
} from "./brandIdentity";

/** Settings → Brand identity (Phase 4b). Read-only by default; "Edit" reveals a
 *  form to edit the workspace's palette, fonts, voice, accent, and logo. The
 *  brand_profile PATCH replaces the profile whole, so Save sends the full
 *  profile (logo included). Disabled for the demo user (server also 403s). */
export function BrandIdentityEditor({ workspace }: { workspace: Workspace }) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const [editing, setEditing] = useState(false);

  if (!editing) {
    return (
      <BrandIdentityView workspace={workspace} canEdit={!isDemo} onEdit={() => setEditing(true)} />
    );
  }
  return (
    <BrandIdentityForm key={workspace.id} workspace={workspace} onDone={() => setEditing(false)} />
  );
}

function BrandIdentityView({
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

function LogoPreview({ url }: { url: string | null }) {
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

function BrandIdentityForm({ workspace, onDone }: { workspace: Workspace; onDone: () => void }) {
  const update = useUpdateWorkspace(workspace.id);
  const uploadLogo = useUploadLogo(workspace.id);
  const deleteLogo = useDeleteLogo(workspace.id);
  const extract = useExtractBrand(workspace.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const extractRef = useRef<HTMLInputElement>(null);
  const [logoError, setLogoError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<BrandExtract | null>(null);

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<BrandForm>({
    resolver: zodResolver(brandSchema),
    defaultValues: toForm(workspace.brand_profile),
  });
  const { fields, append, remove, replace } = useFieldArray({ control, name: "colors" });
  const colors = watch("colors");
  const logo = workspace.brand_profile.logo;
  const uploadedFonts = workspace.brand_profile.uploaded_fonts ?? [];
  const uploadedFamilies = uploadedFonts.map((f) => f.family);

  async function onSubmit(values: BrandForm) {
    setSaveError(null);
    const brand_profile = buildBrandProfile(values, workspace.brand_profile.logo);
    try {
      await update.mutateAsync({ brand_profile });
      onDone();
    } catch {
      setSaveError("Couldn’t save. Try again.");
    }
  }

  async function onLogoFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setLogoError(null);
    try {
      await uploadLogo.mutateAsync(file);
    } catch {
      setLogoError("Upload failed. Use a JPG, PNG, or WebP under 8 MB.");
    }
  }

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

  /** Apply the proposal into the form for review — replaces palette + fonts +
   *  voice. Nothing is saved until the user clicks Save changes. */
  function applyProposal() {
    if (!proposal) return;
    const patch = proposalToForm(proposal);
    replace(patch.colors);
    setValue("fonts.heading", patch.fonts.heading, { shouldDirty: true });
    setValue("fonts.body", patch.fonts.body, { shouldDirty: true });
    setValue("fonts.mono", patch.fonts.mono, { shouldDirty: true });
    setValue("voice_summary", patch.voice_summary, { shouldDirty: true });
    setValue("accent_hex", "", { shouldDirty: true }); // old accent may not be in the new palette
    setProposal(null);
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="flex flex-col gap-6 rounded-xl border border-border bg-surface p-5 shadow-light"
    >
      {/* Learn from an image (Phase 4c) */}
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
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              Proposed — review before applying
            </span>
            <div className="flex flex-wrap gap-2">
              {proposal.colors.map((c) => (
                <span key={`${c.hex}-${c.name}`} className="flex items-center gap-1.5">
                  <span
                    className="h-5 w-5 rounded border border-border"
                    style={{ backgroundColor: c.hex }}
                    aria-hidden
                  />
                  <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                    {c.hex}
                  </span>
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
              <Button type="button" size="sm" onClick={applyProposal}>
                Apply to form
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setProposal(null)}>
                Dismiss
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Applying fills the fields below — review, then <strong>Save changes</strong> to
              persist.
            </p>
          </div>
        )}
      </div>

      {/* Colors */}
      <fieldset className="flex flex-col gap-3">
        <legend className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Colors
        </legend>
        <div className="flex flex-col gap-2.5">
          {fields.map((f, i) => (
            <div key={f.id} className="flex items-start gap-2">
              <input
                type="color"
                aria-label="Color swatch"
                className="mt-0.5 h-10 w-10 shrink-0 cursor-pointer rounded-md border border-border bg-surface"
                value={HEX_RE.test(colors[i]?.hex ?? "") ? colors[i].hex : "#000000"}
                onChange={(e) =>
                  setValue(`colors.${i}.hex`, e.target.value, {
                    shouldValidate: true,
                    shouldDirty: true,
                  })
                }
              />
              <div className="flex flex-1 flex-col gap-1">
                <Input
                  placeholder="Name (e.g. Forest)"
                  aria-label="Color name"
                  className="h-9"
                  aria-invalid={!!errors.colors?.[i]?.name}
                  aria-describedby={errors.colors?.[i]?.name ? `colors-${i}-name-error` : undefined}
                  {...register(`colors.${i}.name` as const)}
                />
                {errors.colors?.[i]?.name && (
                  <span
                    id={`colors-${i}-name-error`}
                    role="alert"
                    className="text-xs text-destructive"
                  >
                    {errors.colors[i]?.name?.message}
                  </span>
                )}
              </div>
              <div className="flex w-28 flex-col gap-1">
                <Input
                  placeholder="#1C3A2E"
                  aria-label="Color hex"
                  className="h-9 font-mono"
                  aria-invalid={!!errors.colors?.[i]?.hex}
                  aria-describedby={errors.colors?.[i]?.hex ? `colors-${i}-hex-error` : undefined}
                  {...register(`colors.${i}.hex` as const)}
                />
                {errors.colors?.[i]?.hex && (
                  <span
                    id={`colors-${i}-hex-error`}
                    role="alert"
                    className="text-xs text-destructive"
                  >
                    {errors.colors[i]?.hex?.message}
                  </span>
                )}
              </div>
              <Select
                aria-label="Color role"
                className="h-9 w-32"
                {...register(`colors.${i}.role` as const)}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </Select>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={() => remove(i)}
                aria-label="Remove color"
                className="mt-0.5 hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          ))}
        </div>
        <div>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => append({ name: "", hex: "#000000", role: "secondary" })}
          >
            <Plus className="h-4 w-4" aria-hidden />
            Add color
          </Button>
        </div>
      </fieldset>

      {/* Accent */}
      <div className="flex flex-col gap-1.5 border-t border-border pt-5">
        <Label htmlFor="accent_hex">Accent (from palette)</Label>
        <Controller
          control={control}
          name="accent_hex"
          render={({ field }) => (
            <Select
              id="accent_hex"
              className="max-w-xs"
              aria-invalid={!!errors.accent_hex}
              aria-describedby={errors.accent_hex ? "accent_hex-error" : undefined}
              {...field}
            >
              <option value="">None</option>
              {colors
                .filter((c) => HEX_RE.test(c.hex))
                .map((c) => (
                  <option key={c.hex} value={c.hex}>
                    {c.name || c.hex} ({c.hex})
                  </option>
                ))}
            </Select>
          )}
        />
        {errors.accent_hex && (
          <span id="accent_hex-error" role="alert" className="text-xs text-destructive">
            {errors.accent_hex.message}
          </span>
        )}
      </div>

      {/* Fonts */}
      <div className="grid gap-3 border-t border-border pt-5 sm:grid-cols-3">
        <div className="flex flex-col">
          <Label htmlFor="font-heading">Heading font</Label>
          <Select id="font-heading" {...register("fonts.heading")}>
            {optionsForRole("heading", watch("fonts.heading"), uploadedFamilies).map((o) => (
              <option key={o.value || "default"} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <FontPreview family={watch("fonts.heading")} uploaded={uploadedFonts} />
        </div>
        <div className="flex flex-col">
          <Label htmlFor="font-body">Body font</Label>
          <Select id="font-body" {...register("fonts.body")}>
            {optionsForRole("body", watch("fonts.body"), uploadedFamilies).map((o) => (
              <option key={o.value || "default"} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <FontPreview family={watch("fonts.body")} uploaded={uploadedFonts} />
        </div>
        <div className="flex flex-col">
          <Label htmlFor="font-mono">Mono font</Label>
          <Select id="font-mono" {...register("fonts.mono")}>
            {optionsForRole("mono", watch("fonts.mono"), uploadedFamilies).map((o) => (
              <option key={o.value || "default"} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <FontPreview family={watch("fonts.mono")} uploaded={uploadedFonts} />
        </div>
      </div>

      {/* Voice */}
      <div className="flex flex-col border-t border-border pt-5">
        <Label htmlFor="voice">Voice summary</Label>
        <Textarea
          id="voice"
          rows={3}
          placeholder="How the brand sounds — tone, vocabulary, what to avoid."
          {...register("voice_summary")}
        />
      </div>

      {/* Logo */}
      <div className="flex flex-col gap-2.5 border-t border-border pt-5">
        <Label>Logo</Label>
        <div className="flex items-center gap-3">
          <LogoPreview url={logo?.url ?? null} />
          <div className="flex items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={onLogoFile}
            />
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => fileRef.current?.click()}
              loading={uploadLogo.isPending}
            >
              <Upload className="h-4 w-4" aria-hidden />
              {logo ? "Replace" : "Upload"}
            </Button>
            {logo && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => deleteLogo.mutate()}
                loading={deleteLogo.isPending}
                className="hover:text-destructive"
              >
                <X className="h-4 w-4" aria-hidden />
                Remove
              </Button>
            )}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Saves immediately. JPG, PNG, or WebP up to 8 MB.
        </p>
        {logoError && (
          <span role="alert" className="text-xs text-destructive">
            {logoError}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 border-t border-border pt-5">
        <Button type="submit" size="sm" loading={isSubmitting || update.isPending}>
          Save changes
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        {saveError && (
          <span role="alert" className="text-xs text-destructive">
            {saveError}
          </span>
        )}
      </div>
    </form>
  );
}

function FontPreview({
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
