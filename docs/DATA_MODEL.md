# Data Model

> MongoDB collections + vector-store schema for Brand Content Studio. Follows [DECISIONS.md](./DECISIONS.md).
> Related: [ARCHITECTURE.md](./ARCHITECTURE.md) · [PLAN.md](./PLAN.md)

Database: `brand_content` (dev: `brand_content_dev`). Five collections (`users`, `workspaces`, `assets`, `generations`, `templates`). Most documents carry UTC `created_at` / `updated_at`. Mongo `ObjectId` is serialized to `str` on the way out (EMS pattern). **Chunk vectors live in the vector store, never in Mongo.**

---

## `users`

Copy the EMS user model. Seed exactly one demo user.

| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `email` | str | unique |
| `hashed_password` | str | passlib/bcrypt |
| `full_name` | str | |
| `is_active` | bool | default true |
| `is_admin` | bool | default false |
| `is_demo` | bool | true for the seeded demo user |
| `created_at` / `updated_at` | datetime | |

**Indexes:** unique `email`.

---

## `workspaces`

| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `owner_id` | ObjectId | → `users._id` |
| `name` | str | e.g. "Verdure Materials" |
| `slug` | str | url-safe, unique per owner |
| `brand_profile` | object | see below |
| `vector_namespace` | str | = `str(_id)`; Chroma collection / Qdrant payload key |
| `embedding_model` | str | `"text-embedding-3-small"` |
| `embedding_dim` | int | `1536` (pinned; a change forces re-ingest) |
| `asset_count` | int | denormalized |
| `ready_chunk_count` | int | denormalized; drives "corpus ready" UI |
| `created_at` / `updated_at` | datetime | |

`brand_profile`:
```jsonc
{
  "colors": [ { "name": "Forest", "hex": "#1C3A2E", "role": "primary" } ],   // role: primary|secondary|neutral|accent
  "accent_hex": "#1C3A2E",        // optional UI tint override (DESIGN §4), cosmetic only
  "fonts": { "heading": "DM Serif Display", "body": "Spectral", "mono": null },  // workspace fonts, NOT app fonts
  "logo": { "storage_key": "…", "url": "…" } | null,
  "voice_summary": "Short cached blurb injected into the prompt header" | null,
  "exemplars":      [ { "id": "…", "storage_key": "…", "url": "…", "style_note": "…" } ],          // past cards → vision style notes (cap 5, Phase 4c)
  "brand_images":   [ { "id": "…", "storage_key": "…", "url": "…", "name": "…" } ],                // reusable image library (cap 24)
  "uploaded_fonts": [ { "id": "…", "family": "…", "storage_key": "…", "url": "…" } ],              // user .ttf brand fonts (cap 8; `family` = the handle used everywhere)
  "card_presets":   [ { "id": "…", "name": "…", "template_id": "photo-led", "accent_hex": "#1C3A2E" | null } ]  // saved card looks (cap 8, Phase 5)
}
```

**Indexes:** `owner_id`; unique `(owner_id, slug)`.

---

## `assets`

| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `workspace_id` | ObjectId | → `workspaces._id` |
| `filename` | str | |
| `content_type` | str | `application/pdf`, `text/markdown`, `text/plain` |
| `asset_kind` | enum | `voice` \| `posts` \| `pillars` \| `personas` \| `competitors` \| `other` |
| `storage_key` | str | local path (dev) or S3 key (prod) |
| `size_bytes` | int | |
| `ingestion_status` | enum | `processing` \| `ready` \| `error` |
| `chunk_count` | int | 0 until ready |
| `error` | str \| null | |
| `ingested_at` | datetime \| null | |
| `created_at` / `updated_at` | datetime | |

**Indexes:** `workspace_id`; `(workspace_id, ingestion_status)`.

---

## `generations`

| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `workspace_id` | ObjectId | |
| `owner_id` | ObjectId | |
| `type` | enum | `text` \| `card` \| `document` \| `post_pack` |
| `brief` | str | the user prompt |
| `status` | enum | `complete` \| `error` |
| `output` | object | discriminated by `type`, see below |
| `retrieved_chunk_ids` | str[] | vector-store ids `{asset_id}:{chunk_index}` |
| `retrieval_meta` | object[] | snapshot for the debug panel + re-open survival (see ARCHITECTURE §5) |
| `model` | str | `"claude-sonnet-4-6"` |
| `embedding_query_model` | str | `"text-embedding-3-small"` |
| `created_at` / `updated_at` | datetime | |

`output` when `type == "text"`:
```jsonc
{ "post_text": "…", "hashtags": ["…"], "char_count": 1287 }
```

`output` when `type == "card"`:
```jsonc
{
  "template_id": "photo-led",            // photo-led | statement | quote
  "fields": { "eyebrow": "…", "headline": "…", "body": "…", "cta": "…", "hashtag": "…" },
  "image": {                             // null until an image is picked
    "source": "unsplash",                // unsplash | upload
    "storage_key": null, "unsplash_id": "abc123", "url": "…",
    "attribution": { "author": "…", "author_url": "…", "source_url": "…" }   // required when source==unsplash
  } | null,
  "suggested_keywords": ["…"],
  "accent_hex": "#1C3A2E" | null         // per-card accent, validated against the palette (Phase 1.5)
}
```

`output` when `type == "document"`:
```jsonc
{
  "document": {
    "archetype": "one-pager",            // one-pager | short-deck
    "title": "…", "eyebrow": "…", "lede": "…",
    "sections": [ { "heading": "…", "body": "…", "bullets": ["…"] } ],
    "footer": "…"
  },
  "formats": { "docx": { "storage_key": "…" }, "pdf": { "storage_key": "…" }, "pptx": { "storage_key": "…" } }  // rendered files, keyed by format
}
```

`output` when `type == "post_pack"` (the "LinkedIn Post" objective — caption + a matching card):
```jsonc
{
  "post_text": "…", "hashtags": ["…"], "char_count": 1287,
  "card": { … }                          // a nested card output (same shape as type=="card" above)
}
```

`retrieval_meta` is **snapshotted onto the generation** so the debug panel and history re-open keep working even if assets are later deleted or re-ingested (vector ids may go stale; the snapshot preview survives).

**Indexes:** `(workspace_id, created_at desc)` (history); `(workspace_id, type)` (history type filter); `(owner_id, created_at desc)` (backs the shared demo account's daily-quota count, SEC-02).

---

## `templates`

Uploaded branded `.docx`/`.pptx` templates (Phase 5). The template's own styling is authoritative — only `{{placeholder}}` text is swapped; renders are returned for immediate download, never persisted.

| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `workspace_id` | ObjectId | → `workspaces._id` |
| `name` | str | sanitized upload filename |
| `format` | enum | `docx` \| `pptx` |
| `storage_key` | str | the uploaded template file |
| `placeholders` | str[] | discovered `{{names}}` (docxtpl Jinja analysis / pptx paragraph scan) |
| `created_at` | datetime | |

**Indexes:** `workspace_id`.

---

## Vector store schema

Not Mongo — Chroma (dev) / Qdrant (prod). One logical record per chunk:

| Field | Value |
|---|---|
| id | `{asset_id}:{chunk_index}` |
| vector | 1536-dim, cosine |
| payload / metadata | `{ workspace_id, asset_id, filename, asset_kind, chunk_index, page? }` |
| text | the chunk content (stored in payload/document) |

- **Chroma:** collection per workspace `ws_{workspace_id}`.
- **Qdrant:** single collection `brand-content-studio`; isolation via **indexed** payload filter `workspace_id`.

Identical payloads across both backends → switching `vector_store_backend` is config-only.
