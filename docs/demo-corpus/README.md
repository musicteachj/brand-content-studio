# Verdure Materials — Demo Corpus

> The seed brand corpus for the portfolio demo. **Corpus quality is the demo** (DECISIONS #10, ARCHITECTURE gotcha #5): a thin corpus produces generic output and makes RAG look pointless. These files are rich on purpose.

**Demo brand:** Verdure Materials — a B2B supplier of low-carbon, bio-based building materials (mycelium panels, hempcrete blocks, reclaimed-timber cladding) for architects and sustainable developers. Forest green `#1C3A2E`, cream `#F4F1E9`, gold/ochre `#C98A3D`, serif typography (DM Serif Display headings, Spectral body).

## Files → `asset_kind` mapping

These map directly onto the `assets.asset_kind` enum (see [../DATA_MODEL.md](../DATA_MODEL.md)). At build time they are copied/converted into `server/seed/verdure_corpus/` and ingested by `seed_demo.py`.

| File | `asset_kind` | Ingestion note |
|---|---|---|
| `voice-and-tone.md` | `voice` | standard 800/120 chunking |
| `past-posts.md` | `posts` | **one chunk per post** (split on the `---` delimiter) — highest-value retrieval target |
| `content-pillars.md` | `pillars` | standard chunking |
| `personas.md` | `personas` | standard chunking |
| `competitors.md` | `competitors` | standard chunking |

## Notes for the build

- A PDF version of `voice-and-tone.md` should exist too, so the demo exercises the **pdfplumber** path (not just markdown). Generate it from the markdown.
- `workspace.brand_profile.voice_summary` should be a 1–2 sentence distillation of `voice-and-tone.md` (cached for the prompt header).
- Everything here is fictional and written for demo purposes.
