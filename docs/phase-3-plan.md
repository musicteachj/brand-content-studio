# Phase 3 — "LinkedIn Post" objective (slice plan)

> **Status: built + verified on `feat/3-post-pack`.** Server gate (ruff + mypy + 43 pytest) and
> client gate (tsc + eslint + prettier + build + 27 vitest) green; **live acceptance run passed**
> (one brief → a streamed caption + a distilled, coherent card in Verdure brand; image attach into
> the nested card; copy/export with no `/generate`). Tier-2 review gate done (`/code-review`:
> clean — reuse-heavy, one minor polish note; `/security-review`: clean — no new surface). Pending:
> commit → push → PR into `dev`; phase boundary `dev → main` + tag `v0.5.0`.
>
> The first phase of the pre-deployment enhancements plan. Follows the approved roadmap (LinkedIn-post
> objective → brand setup & learning → on-brand templates → robustness) and [WORKFLOW.md](./WORKFLOW.md).

## Goal

One brief → a full LinkedIn **post caption** *and* a matching **card**, built together, so the user
gets something to post plus the copy to post with it. The first **objective** (vs. a raw format) —
the marriage of Phase 1a (caption) + 1b (card), with near-total reuse.

**Acceptance:** a single brief produces a streamed, on-brand caption and a coherent card (the card is
the post's hook); an image attaches to the card; caption-copy and card-export make no `/generate`
call; the pair persists and re-opens from History.

## Design (confirmed)

- **Flow:** one hybrid retrieval → **stream the caption** (reuse `prompts/text_post.py` +
  `generation_service.stream_text`) → **distill the card from the finished caption** via forced
  strict tool-use (reuse `image_card.CARD_FIELDS_TOOL`; new `prompts/post_pack.py` distill prompt).
  The card is the post's hook, compressed — not a copy. The distill runs on the model's own caption,
  so no new `<brand_context>` injection surface.
- **Data:** `GenerationType.post_pack`; `output` = caption (`TextOutput` shape) + the card **nested**
  under `output.card` (`CardOutput` shape). No new collection.
- **PATCH:** image-attach / customization routes into `output.card` via a new `nested_key` arg on
  `update_generation_output` (a `card` still merges at the top); the accent-palette guard holds.
- **Client:** a new "LinkedIn post" Generate mode — `CardPreview` (reused) beside `PostCaptionPanel`
  (streams live → editable, copyable textarea); parallel image pick via `ImagePickerPanel`;
  `usePostPackGeneration` mirrors `useCardGeneration`. History: LinkedIn filter + post_pack rendering
  + Customize hydration.

## Reuse (do NOT rebuild)

`retrieval_service`, `text_post`, `stream_text`, `extract_card_fields` + `CARD_FIELDS_TOOL`,
`parse_post`, `build_card_output`, `CardPreview` / `cards/cardElement` / `useCardExport`,
`ImagePickerPanel`, `PATCH /generations/{id}`, the History grid/detail + `useGenerationActions`.
Genuinely new: the `post_pack` type/output, the distill prompt, `usePostPackGeneration`,
`PostControlsPanel`, `PostCaptionPanel`, and the combined-mode layout.

## Tests

- pytest: `/generate/post` streams the caption + distills/persists the nested card (image null until
  PATCH); empty corpus blocks Claude; PATCH attaches an image into `output.card` (not top-level) with
  the accent guard.
- vitest: `usePostPackGeneration` hydrates a re-opened post_pack; an image selection PATCHes the
  generation and **never** calls `/generate`.

## Review gate

Reuse-heavy, low new surface → **Tier 1–2**: `/code-review` + `/security-review` before the first
push. No new deps/uploads/external calls. No commit/push without explicit approval. Fold UI into
DESIGN.md (done); CHANGELOG `0.5.0` + DECISIONS #22 at phase end.

## Follow-ups (not in this slice)

- Full post-card customization (layout/accent/inline-copy editor) for the post_pack card — only image
  swap is wired now; the card editor (`useCardEditor`/`CardCustomizePanel`) could be threaded onto the
  nested card later.
- Persisting caption edits (currently the edited caption is local/paste-ready, not PATCHed back).
- The card panel shows a "Writing…" drafting state during caption-only streaming — could become a
  "card follows the caption" placeholder.
