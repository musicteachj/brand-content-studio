// Shared API contract types — mirror server/app/models (Pydantic v2).
// Keep in sync with the backend; these are the front/back contract (WORKFLOW §2).

export type ColorRole = "primary" | "secondary" | "neutral" | "accent";

export interface BrandColor {
  name: string;
  hex: string;
  role: ColorRole;
}

export interface BrandFonts {
  heading: string | null;
  body: string | null;
  mono: string | null;
}

export interface BrandLogo {
  storage_key: string;
  url: string | null;
}

export interface BrandExemplar {
  id: string;
  storage_key: string;
  url: string | null;
  style_note: string;
}

export interface BrandImage {
  id: string;
  storage_key: string;
  url: string | null;
  name: string | null;
}

export interface BrandProfile {
  colors: BrandColor[];
  accent_hex: string | null;
  fonts: BrandFonts;
  logo: BrandLogo | null;
  voice_summary: string | null;
  exemplars: BrandExemplar[];
  brand_images: BrandImage[];
}

// Phase 4c — a proposed brand profile inferred from an uploaded image. Returned
// by POST /workspaces/{id}/brand/extract for review; applied via the brand PATCH.
export interface BrandExtract {
  colors: BrandColor[];
  voice_summary: string | null;
  fonts: BrandFonts;
}

export interface Workspace {
  id: string;
  owner_id: string;
  name: string;
  slug: string;
  brand_profile: BrandProfile;
  vector_namespace: string;
  embedding_model: string;
  embedding_dim: number;
  asset_count: number;
  ready_chunk_count: number;
  created_at: string | null;
  updated_at: string | null;
}

// Phase 5 — on-brand document templates.
export type TemplateFormat = "docx" | "pptx";

export interface Template {
  id: string;
  workspace_id: string;
  name: string;
  format: TemplateFormat;
  storage_key: string;
  placeholders: string[];
  created_at: string | null;
}

export type AssetKind = "voice" | "posts" | "pillars" | "personas" | "competitors" | "other";

export type IngestionStatus = "processing" | "ready" | "error";

export interface Asset {
  id: string;
  workspace_id: string;
  filename: string;
  content_type: string;
  asset_kind: AssetKind;
  size_bytes: number;
  ingestion_status: IngestionStatus;
  chunk_count: number;
  error: string | null;
  ingested_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export type GenerationType = "text" | "card" | "document" | "post_pack";
export type GenerationStatus = "complete" | "error";
export type Tone = "default" | "confident" | "warm" | "technical" | "provocative";
export type Length = "short" | "medium" | "long";
export type CardTemplate = "photo-led" | "statement" | "quote";
export type DocumentArchetype = "one-pager" | "short-deck";
export type DocumentFormat = "docx" | "pdf" | "pptx";

export interface TextGenerateRequest {
  brief: string;
  tone: Tone;
  length: Length;
}

export interface CardGenerateRequest {
  brief: string;
  template_id: CardTemplate;
  tone: Tone;
}

export interface DocumentGenerateRequest {
  brief: string;
  archetype: DocumentArchetype;
  tone: Tone;
}

export interface PostPackGenerateRequest {
  brief: string;
  tone: Tone;
  template_id: CardTemplate;
}

export interface TextOutput {
  post_text: string;
  hashtags: string[];
  char_count: number;
}

export interface CardFields {
  eyebrow: string;
  headline: string;
  body: string;
  cta: string;
  hashtag: string;
}

export interface ImageAttribution {
  author: string;
  author_url: string;
  source_url: string;
}

export interface CardImage {
  source: "unsplash" | "upload";
  url: string | null;
  storage_key: string | null;
  unsplash_id: string | null;
  attribution: ImageAttribution | null;
}

export interface CardOutput {
  template_id: CardTemplate;
  fields: CardFields;
  image: CardImage | null;
  suggested_keywords: string[];
  // Phase 1.5: which brand-palette color this card uses as its accent
  // (null = the brand's default accent role).
  accent_hex: string | null;
}

// Phase 2 — document output. One structured model is rendered server-side into
// each branded format; the files are pulled through an auth-gated download route.
export interface DocumentSection {
  heading: string;
  body: string;
  bullets: string[];
}

export interface DocumentModel {
  archetype: DocumentArchetype;
  title: string;
  eyebrow: string;
  lede: string;
  sections: DocumentSection[];
  footer: string;
}

export interface DocumentFormatRef {
  storage_key: string;
}

export interface DocumentOutput {
  document: DocumentModel;
  formats: Partial<Record<DocumentFormat, DocumentFormatRef>>;
}

// Phase 3 — the "LinkedIn Post" objective. One generation holds the post caption
// (TextOutput shape) plus the matching card nested under `card` (CardOutput shape).
// PATCH (image attach / customization) targets `output.card` server-side.
export interface PostPackOutput {
  post_text: string;
  hashtags: string[];
  char_count: number;
  card: CardOutput;
}

// Phase 1.5 client-side customization — partial PATCH onto a card's `output`.
// Every field is a no-/generate edit (layout swap, inline copy, accent).
export interface GenerationUpdate {
  template_id?: CardTemplate;
  fields?: CardFields;
  image?: CardImage;
  accent_hex?: string;
}

// Unsplash search results (server-proxied, attribution normalized).
export interface UnsplashPhoto {
  id: string;
  description: string | null;
  thumb_url: string;
  preview_url: string;
  width: number;
  height: number;
  color: string | null;
  attribution: ImageAttribution;
  download_location: string;
}

export interface UnsplashSearchResponse {
  query: string;
  page: number;
  total_pages: number;
  results: UnsplashPhoto[];
}

export interface ImageUploadResponse {
  source: "upload";
  storage_key: string;
  url: string;
}

export interface RetrievalMetaItem {
  chunk_id: string;
  asset_id: string;
  filename: string;
  asset_kind: string;
  score: number;
  preview: string;
  chunk_index: number;
  page: number | null;
  pinned: boolean;
}

export interface Generation {
  id: string;
  workspace_id: string;
  owner_id: string;
  type: GenerationType;
  brief: string;
  status: GenerationStatus;
  output: TextOutput | DocumentOutput | PostPackOutput | Record<string, unknown>;
  retrieved_chunk_ids: string[];
  retrieval_meta: RetrievalMetaItem[];
  model: string;
  embedding_query_model: string;
  created_at: string | null;
  updated_at: string | null;
}

// Phase 6 — paginated list envelopes ({items, next_offset}; null = exhausted).
export interface GenerationPage {
  items: Generation[];
  next_offset: number | null;
}

export interface AssetPage {
  items: Asset[];
  next_offset: number | null;
}

// SSE frame shapes from /generate/text (lib/sse.ts decodes these).
export interface SSETextFrame {
  text: string;
}
export interface RetrievalEnvelope {
  k: number;
  retrieved: RetrievalMetaItem[];
  embedding_model: string;
  latency_ms: number;
}
export interface SSEMetaFrame {
  meta: {
    generation_id: string;
    retrieval: RetrievalEnvelope;
  };
}
// Terminal meta for /generate/card — carries the structured fields + image
// keywords alongside the retrieval snapshot.
export interface SSECardMetaFrame {
  meta: {
    generation_id: string;
    template_id: CardTemplate;
    fields: CardFields;
    suggested_keywords: string[];
    retrieval: RetrievalEnvelope;
  };
}
// Terminal meta for /generate/document — the structured model + the per-format
// storage keys, alongside the retrieval snapshot.
export interface SSEDocumentMetaFrame {
  meta: {
    generation_id: string;
    archetype: DocumentArchetype;
    document: DocumentModel;
    formats: Partial<Record<DocumentFormat, DocumentFormatRef>>;
    retrieval: RetrievalEnvelope;
  };
}
export interface SSEErrorFrame {
  error: string;
}
