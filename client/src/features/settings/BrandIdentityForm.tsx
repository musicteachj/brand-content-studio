import { useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2, Upload, X } from "lucide-react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { optionsForRole } from "@/styles/fontCatalog";
import { useDeleteLogo, useUpdateWorkspace, useUploadLogo } from "@/api/workspaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { BrandExtract, Workspace } from "@/types";
import {
  brandSchema,
  buildBrandProfile,
  HEX_RE,
  proposalToForm,
  ROLES,
  toForm,
  type BrandForm,
} from "./brandIdentity";
import { BrandExtractPanel } from "./BrandExtractPanel";
import { FontPreview } from "./FontPreview";
import { LogoPreview } from "./LogoPreview";

export function BrandIdentityForm({
  workspace,
  onDone,
}: {
  workspace: Workspace;
  onDone: () => void;
}) {
  const update = useUpdateWorkspace(workspace.id);
  const uploadLogo = useUploadLogo(workspace.id);
  const deleteLogo = useDeleteLogo(workspace.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [logoError, setLogoError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

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

  /** Apply an extract proposal into the form for review — replaces palette + fonts
   *  + voice. Nothing is saved until the user clicks Save changes. */
  function applyProposal(proposal: BrandExtract) {
    const patch = proposalToForm(proposal);
    replace(patch.colors);
    setValue("fonts.heading", patch.fonts.heading, { shouldDirty: true });
    setValue("fonts.body", patch.fonts.body, { shouldDirty: true });
    setValue("fonts.mono", patch.fonts.mono, { shouldDirty: true });
    setValue("voice_summary", patch.voice_summary, { shouldDirty: true });
    setValue("accent_hex", "", { shouldDirty: true }); // old accent may not be in the new palette
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="flex flex-col gap-6 rounded-xl border border-border bg-surface p-5 shadow-light"
    >
      <BrandExtractPanel workspaceId={workspace.id} onApply={applyProposal} />

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
