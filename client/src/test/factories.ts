import type { BrandProfile, Generation } from "@/types";

/** A complete BrandProfile for tests. Spread overrides on top of the empty
 *  defaults so that adding a field to BrandProfile breaks this file only,
 *  instead of every fixture that constructs one by hand. */
export function makeBrandProfile(overrides: Partial<BrandProfile> = {}): BrandProfile {
  return {
    colors: [],
    accent_hex: null,
    fonts: { heading: null, body: null, mono: null },
    logo: null,
    voice_summary: null,
    exemplars: [],
    brand_images: [],
    uploaded_fonts: [],
    card_presets: [],
    ...overrides,
  };
}

/** A complete Generation for tests/MSW handlers — same rationale as makeBrandProfile:
 *  a new required field on Generation breaks this file only. */
export function makeGeneration(overrides: Partial<Generation> = {}): Generation {
  return {
    id: "gen1",
    workspace_id: "ws1",
    owner_id: "owner1",
    type: "text",
    brief: "brief",
    status: "complete",
    output: { post_text: "Hello" },
    retrieved_chunk_ids: [],
    retrieval_meta: [],
    model: "claude-test",
    embedding_query_model: "text-embedding-test",
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}
