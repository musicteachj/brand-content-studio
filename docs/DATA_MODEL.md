# Data Model

> MongoDB collections + vector-store schema for Brand Content Studio. Follows [DECISIONS.md](./DECISIONS.md).
> Related: [ARCHITECTURE.md](./ARCHITECTURE.md) · [PLAN.md](./PLAN.md)

Database: `folio` (set by `DATABASE_NAME`; a local `.env` from before the rename may keep `brand_content`, and the test suite uses its own test database). Nine collections (`users`, `workspaces`, `assets`, `generations`, `templates`, `demo_sessions`, `ai_spend_days`, `ai_spend_calls`, `ai_spend_visitors`; the `usage` collection is gone). Most documents carry UTC `created_at` / `updated_at`. Mongo `ObjectId` is serialized to `str` on the way out (EMS pattern). **Chunk vectors live in the vector store, never in Mongo.**

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
| `vector_namespace` | str | = `str(_id)`; the Chroma collection name suffix (`ws_{id}`) |
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
| `session_id` | str | the visitor session that made it; set only on a visitor's generations (never returned by the API) |
| `expires_at` | datetime | the session's expiry; the hourly cleanup job removes the generation, its files first, after it. Set only on a visitor's generations |
| `is_example` | bool | true for the four read-only ready-made examples (readable by everyone, never changed or deleted through the API) |
| `example_key` | str | the example's stable key, set only on examples; the seed finds and repairs examples by it |
| `model` | str | `"claude-sonnet-5-5"` (rows saved before DECISIONS #40 keep `"claude-sonnet-4-6"`) |
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

**Indexes:** `(workspace_id, created_at desc)` (history); `(workspace_id, type)` (history type filter); `(workspace_id, session_id, created_at desc)` (a visitor's History); `expires_at` (the cleanup job; deliberately not a TTL index, so files go before records); unique `(workspace_id, example_key)` with a partial filter on `example_key` existing (one of each example per workspace). `ensure_indexes` drops the old global `example_key_1` index and the old `(owner_id, created_at desc)` quota index where they still exist.

Every read and write goes through `generations_service.scope_filter`: the owner reaches the whole workspace, a visitor only their own `session_id` plus `is_example` documents.

---

## `templates`

Uploaded branded `.docx`/`.pptx` templates (Phase 5). The template's own styling is authoritative — only `{{placeholder}}` text is swapped; renders are returned for immediate download, never persisted.

| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `workspace_id` | ObjectId | → `workspaces._id` |
| `owner_id` | ObjectId | → `users._id`, the uploader |
| `name` | str | sanitized upload filename |
| `format` | enum | `docx` \| `pptx` |
| `storage_key` | str | the uploaded template file |
| `placeholders` | str[] | discovered `{{names}}` (docxtpl Jinja analysis / pptx paragraph scan) |
| `created_at` | datetime | |

**Indexes:** `workspace_id`.

---

## `demo_sessions`

One document per demo start (DECISIONS #41). The ID rides in the visitor's JWT as `sid`; a token is good only while its session exists and has not expired.

| Field | Type | Notes |
|---|---|---|
| `_id` | str | random 43-character URL-safe ID |
| `user_id` | ObjectId | → `users._id`, the demo user |
| `created_at` | datetime | |
| `expires_at` | datetime | `created_at` + 24 hours |

**Indexes:** `expires_at` (not a TTL index: the cleanup job removes a session's work and spend with it).

---

## AI dollar ledger (DECISIONS #42)

Three collections in integer micro-dollars (1 USD = 1,000,000). No TTL on spend; nothing here is the old `usage` collection.

`ai_spend_days`: settled plus open spend for one UTC day.

| Field | Type | Notes |
|---|---|---|
| `_id` | str | `YYYY-MM-DD` (UTC) |
| `month` | str | the month the day belongs to (pacing reads one month of days) |
| `total_micros` | int | settled + open reservations that day |

`ai_spend_calls`: one document per reserved call.

| Field | Type | Notes |
|---|---|---|
| `_id` | | the reservation's ID |
| `day`, `month` | str | dated on the reservation's own day |
| `visitor_id` | str \| null | the demo session ID; null for owner and seed calls |
| `provider`, `model`, `purpose` | str | e.g. Anthropic, `claude-sonnet-5-5`, what the call was for |
| `reserved_micros` | int | the worst-case cost taken before the call |
| `actual_micros` | int \| null | the settled cost; null while open |
| `status` | enum | `open` \| `settled` \| `swept` (charged by the sweeper after 10 minutes) |
| `outcome` | str | how it ended (for example a billed success, `canceled_or_unknown`, `not_attempted`) |
| `created_at` / `settled_at` | datetime | |

`ai_spend_visitors`: a visitor session's running spend.

| Field | Type | Notes |
|---|---|---|
| `_id` | str | the session ID (`demo_sessions._id`) |
| `total_micros` | int | settled + open spend; a call is admitted while this is below `AI_VISITOR_BUDGET_USD` |

**Indexes:** `ai_spend_calls (status, created_at)` (the sweeper and prune); `ai_spend_days month`. The cleanup job prunes closed (settled or swept) call records older than 35 days (day totals are kept) and deletes an expired session's `ai_spend_visitors` document.

---

## Vector store schema

Not Mongo: Chroma, in-process on local disk (`CHROMA_PATH`), in development and in production (DECISIONS #44). One logical record per chunk:

| Field | Value |
|---|---|
| id | `{asset_id}:{chunk_index}` |
| vector | 1536-dim, cosine |
| payload / metadata | `{ workspace_id, asset_id, filename, asset_kind, chunk_index, page? }` |
| text | the chunk content (stored in payload/document) |

- **Chroma:** one collection per workspace, `ws_{workspace_id}`, pinned to 1536 dimensions and cosine. The seed rebuilds the demo workspace's collection from `server/seed/fixtures/verdure_embeddings.json` (32 chunks keyed by the sha256 of their text) when its count differs from the assets' total `chunk_count`.
