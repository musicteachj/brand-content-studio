import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { CardFields, CardTemplate, GenerationUpdate } from "@/types";

/** The card's persisted customization state, the editor's seed + save baseline. */
export interface CardEditorBase {
  generationId: string | null;
  template: CardTemplate;
  fields: CardFields;
  accentHex: string | null;
}

interface Draft {
  template: CardTemplate;
  fields: CardFields;
  accentHex: string | null;
}

function toDraft(base: CardEditorBase): Draft {
  return { template: base.template, fields: { ...base.fields }, accentHex: base.accentHex };
}

function cloneDraft(d: Draft): Draft {
  return { template: d.template, fields: { ...d.fields }, accentHex: d.accentHex };
}

function fieldsEqual(a: CardFields, b: CardFields): boolean {
  return (
    a.eyebrow === b.eyebrow &&
    a.headline === b.headline &&
    a.body === b.body &&
    a.cta === b.cta &&
    a.hashtag === b.hashtag
  );
}

function draftEqual(a: Draft, b: Draft): boolean {
  return (
    a.template === b.template && a.accentHex === b.accentHex && fieldsEqual(a.fields, b.fields)
  );
}

/** Client-side card customization (Phase 1.5): layout swap, inline copy edits, and
 *  the per-card accent. Edits are a local draft rendered live in the preview;
 *  nothing persists until an explicit Save, which PATCHes only the changed keys
 *  onto the generation's `output` — NEVER a `/generate` call. Discard resets to
 *  the last-saved baseline. Re-seeds when a different generation is loaded. */
export function useCardEditor(workspaceId: string | null, base: CardEditorBase | null) {
  const [draft, setDraft] = useState<Draft | null>(base ? toDraft(base) : null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // The last-persisted draft — what Save diffs against and Discard reverts to.
  const baselineRef = useRef<Draft | null>(base ? toDraft(base) : null);
  // Re-seed only when the underlying generation changes (not on every keystroke
  // upstream), so in-progress edits aren't clobbered by parent re-renders.
  const seededIdRef = useRef<string | null>(base?.generationId ?? null);

  useEffect(() => {
    if (!base) {
      setDraft(null);
      baselineRef.current = null;
      seededIdRef.current = null;
      return;
    }
    if (base.generationId !== seededIdRef.current) {
      seededIdRef.current = base.generationId;
      const seeded = toDraft(base);
      baselineRef.current = seeded;
      setDraft(seeded);
      setSaveError(null);
    }
  }, [base]);

  const dirty = !!draft && !!baselineRef.current && !draftEqual(draft, baselineRef.current);

  const setTemplate = useCallback((template: CardTemplate) => {
    setDraft((d) => (d ? { ...d, template } : d));
  }, []);

  const setAccent = useCallback((accentHex: string | null) => {
    setDraft((d) => (d ? { ...d, accentHex } : d));
  }, []);

  const setField = useCallback((key: keyof CardFields, value: string) => {
    setDraft((d) => (d ? { ...d, fields: { ...d.fields, [key]: value } } : d));
  }, []);

  const discard = useCallback(() => {
    if (baselineRef.current) setDraft(cloneDraft(baselineRef.current));
    setSaveError(null);
  }, []);

  const save = useCallback(async (): Promise<boolean> => {
    if (!workspaceId || !draft || !base?.generationId || !baselineRef.current) return false;
    const baseline = baselineRef.current;
    const patch: GenerationUpdate = {};
    if (draft.template !== baseline.template) patch.template_id = draft.template;
    if (!fieldsEqual(draft.fields, baseline.fields)) patch.fields = draft.fields;
    if (draft.accentHex !== baseline.accentHex && draft.accentHex)
      patch.accent_hex = draft.accentHex;
    if (Object.keys(patch).length === 0) return true;

    setSaving(true);
    setSaveError(null);
    try {
      await api.patch(`/workspaces/${workspaceId}/generations/${base.generationId}`, patch);
      baselineRef.current = { ...draft };
      return true;
    } catch {
      setSaveError("Couldn’t save your changes. Try again.");
      return false;
    } finally {
      setSaving(false);
    }
  }, [workspaceId, draft, base?.generationId]);

  return {
    template: draft?.template ?? base?.template ?? "photo-led",
    fields: draft?.fields ?? base?.fields ?? null,
    accentHex: draft?.accentHex ?? base?.accentHex ?? null,
    dirty,
    saving,
    saveError,
    setTemplate,
    setAccent,
    setField,
    discard,
    save,
  };
}
