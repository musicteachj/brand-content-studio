# Example-card exemplar steering — design (Phase 4c, PR-C)

## Context

Phase 4 makes Brand Content Studio multi-brand and self-describing: workspace switcher +
manage (PR #7), an in-app brand editor + logo (PR #7), and **brand auto-extract** — propose a
palette/voice/fonts from an uploaded image (PR #8). The remaining half of slice 4c is **learning the
brand from real examples**: let the owner upload their past on-brand cards and have generated copy
*steer toward* those examples.

This is the "learn from examples" thesis of the pre-deployment round (PLAN R2 / DECISIONS #23). The
honesty stance is fixed: we **approximate via our Satori archetypes + extracted brand direction — we
never pixel-clone** an uploaded card.

The generation seam is already in place. Every generate route reads
`brand_profile.voice_summary` and passes it to `build_system(...)`, which appends a trusted
"Brand voice summary (authoritative)" block to the system prompt
(`server/app/prompts/text_post.py:39`, `image_card.py:61`, used in `routes/generate.py`). Exemplar
guidance rides that exact pattern.

## Decisions (owner-confirmed)

1. **Pre-extract to text on upload**, not per-generation multimodal. One vision call at upload time
   stores a short text `style_note`; generation injects text only — cheap, fast, reviewable, and
   consistent with 4c auto-extract and `voice_summary`.
2. **Store on `brand_profile.exemplars`** (embedded list, capped at 5), not a separate collection.
   Reuses the logo storage + targeted-update pattern; the generate routes already load
   `brand_profile`, so guidance costs zero extra reads and cascades on workspace delete.
3. **Inject into the generate trio** — text, card, post_pack — not documents (the exemplars are
   *cards*; documents are a different medium and can be added later).

## Architecture

End-to-end reuse of the logo + 4c-extract patterns.

**Upload flow:** validate image (allow-list + size) → **extract `style_note` via one forced strict
Claude-vision tool-use call** → store the image bytes via `StorageBackend` → `$push` a
`BrandExemplar` onto `brand_profile.exemplars`. Extraction runs **before** storage so a vision
failure leaves nothing persisted (no orphan bytes, no note-less exemplar).

**Generation flow:** each route reads `brand_profile.exemplars`, joins the notes via
`build_exemplar_guidance(notes)`, and passes the result into the existing `build_system(...)` /
`build_copy_system(...)`, which append an "On-brand examples to emulate (your own past cards)" block
after the voice summary. post_pack's caption uses `text_post.build_system`, so it is covered; the
card-distill step operates on the finished caption and needs no exemplar input.

## Data model (`server/app/models/common.py`)

```python
class BrandExemplar(BaseModel):
    id: str                      # str(ObjectId), server-generated
    storage_key: str
    url: Optional[str] = None
    style_note: str              # the extracted copy/visual direction

class BrandProfile(BaseModel):
    ...
    exemplars: list[BrandExemplar] = Field(default_factory=list)
```

`MAX_EXEMPLARS = 5`. Client `types/index.ts` mirrors `BrandExemplar` + `exemplars`.

## Server components

- **`prompts/brand_extract.py`** — add `EXEMPLAR_NOTE_TOOL` (strict, single `style_note` string) +
  `build_exemplar_system()` / `build_exemplar_user()`. The system prompt says: describe the copy
  patterns (rhythm, length, diction) and visual direction (mood, composition) to *emulate via our
  archetypes*; **do not** instruct a pixel-faithful clone; keep it to 1–3 sentences.
- **`services/brand_extract_service.py`** — `propose_exemplar_note(data, media_type) -> str` (a
  vision tool-use call mirroring `propose`; returns the trimmed note).
- **`services/workspace_service.py`** — `add_workspace_exemplar(db, ws_id, owner_id, exemplar)`
  (`$push`) and `remove_workspace_exemplar(db, ws_id, owner_id, exemplar_id) -> (WorkspaceResponse,
  old_key|None)` (`$pull` + return the storage key to delete). Targeted updates, like the logo.
- **`prompts/exemplars.py`** (small, shared) — `build_exemplar_guidance(notes: list[str]) -> str |
  None`: joins non-empty notes into the trusted block, or `None` when empty.
- **`prompts/text_post.py` + `image_card.py`** — `build_system` / `build_copy_system` gain an
  optional `exemplar_guidance: str | None` appended after the voice summary.
- **`routes/workspaces.py`:**
  - `POST /workspaces/{id}/exemplars` (multipart, image-only): `get_workspace_or_404` +
    `require_not_demo`; validate type/size/empty; **409 if `len(exemplars) >= MAX_EXEMPLARS`**;
    extract note → store bytes (`build_image_key`) → `add_workspace_exemplar`; returns the updated
    `WorkspaceResponse`.
  - `DELETE /workspaces/{id}/exemplars/{exemplar_id}`: `require_not_demo`; `remove_workspace_exemplar`
    → delete the stored bytes; returns the updated `WorkspaceResponse`.
- **`routes/generate.py`** — the three routes read `brand_profile.exemplars`, build guidance, and
  pass it into the system builders.

## Client components

- **`api/workspaces.ts`** — `useAddExemplar(wsId)` (multipart) and `useRemoveExemplar(wsId)`; both
  invalidate `["workspace", id]` + `["workspaces"]`.
- **`features/settings/ExemplarsSection.tsx`** — a Settings sub-section under Brand identity: a grid
  of exemplar thumbnails (loaded via `fetchImageDataUrl`) each with its `style_note` + a remove
  button, plus an "Add example card" upload that shows an extracting state. Persists immediately
  (like the logo), independent of the brand-form Save. Add disabled at cap / for the demo user;
  delete demo-disabled. Rendered from `SettingsPage`.

## Error handling

- Upload: 415 (bad type) / 413 (oversize) / 400 (empty), mirroring the logo route.
- **409 at cap** with a friendly message; the client disables Add and shows "5 of 5".
- Vision-extraction failure → surfaced error + retry; nothing persisted (extract-before-store).
- All mutations `require_not_demo` (they persist), and the UI disables them for `is_demo` so client
  and server agree.

## Testing

- **pytest:** add appends a `BrandExemplar` (vision **faked** — no model call), stores the bytes,
  enforces the cap (409 at MAX), is demo-blocked (403), rejects bad type/size/empty; remove `$pull`s
  the entry and deletes the stored bytes; `build_exemplar_guidance` joins notes and returns `None`
  when empty; `build_system` / `build_copy_system` include the block when guidance is present and
  omit it when absent.
- **vitest:** `ExemplarsSection` renders thumbnails + notes and removes one; Add disabled at cap and
  for demo.

## Out of scope (YAGNI / deferred)

- Editing or re-extracting a stored note; reordering exemplars.
- Injecting exemplar guidance into **document** generation.
- A separate synthesis model call (notes are concatenated as-is).
- Pixel-faithful card cloning (explicitly never — DECISIONS #23 honesty stance).

## Verification

Stack: `docker-compose up` + server (`env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m
uvicorn app.main:app --port 8000`) + `npm run dev`. Live: upload 1–2 past cards in Settings → see a
sensible extracted note → generate a card/post and confirm the copy leans toward the exemplars'
style; remove an exemplar; confirm the 5-cap and demo-disable. Per-PR gate: server ruff + mypy +
pytest; client tsc + eslint + prettier + build + vitest; then `/code-review` + `/security-review`,
owner commit/push approval, PR into `dev`.
