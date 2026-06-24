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

export interface BrandProfile {
  colors: BrandColor[];
  accent_hex: string | null;
  fonts: BrandFonts;
  logo: BrandLogo | null;
  voice_summary: string | null;
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

export type GenerationType = "text" | "card";
export type GenerationStatus = "complete" | "error";
export type Tone = "default" | "confident" | "warm" | "technical" | "provocative";
export type Length = "short" | "medium" | "long";

export interface TextGenerateRequest {
  brief: string;
  tone: Tone;
  length: Length;
}

export interface TextOutput {
  post_text: string;
  hashtags: string[];
  char_count: number;
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
  output: TextOutput | Record<string, unknown>;
  retrieved_chunk_ids: string[];
  retrieval_meta: RetrievalMetaItem[];
  model: string;
  embedding_query_model: string;
  created_at: string | null;
  updated_at: string | null;
}

// SSE frame shapes from /generate/text (lib/sse.ts decodes these).
export interface SSETextFrame {
  text: string;
}
export interface SSEMetaFrame {
  meta: {
    generation_id: string;
    retrieval: {
      k: number;
      retrieved: RetrievalMetaItem[];
      embedding_model: string;
      latency_ms: number;
    };
  };
}
export interface SSEErrorFrame {
  error: string;
}
