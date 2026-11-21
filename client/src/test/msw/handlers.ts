import { http, HttpResponse } from "msw";
import type { AppStatus } from "@/api/status";
import type { AuthUser } from "@/stores/auth";
import { makeGeneration } from "@/test/factories";
import type { ExamplesResponse, Generation, GenerationPage } from "@/types";

/** The four ready-made examples GET /api/examples serves, one of each kind, in display
 *  order. The brand sets no fonts, so no test reaches a font CDN. */
export const EXAMPLE_ITEMS: Generation[] = [
  makeGeneration({
    id: "ex-text",
    workspace_id: "demo-ws",
    type: "text",
    brief: "A post on when hempcrete is worth its cost premium.",
    output: { post_text: "Hempcrete locks away carbon.", hashtags: [], char_count: 28 },
    is_example: true,
  }),
  makeGeneration({
    id: "ex-card",
    workspace_id: "demo-ws",
    type: "card",
    brief: "A statement card on why every material claim needs a number.",
    output: {
      template_id: "statement",
      fields: {
        eyebrow: "Evidence first",
        headline: "Show the numbers.",
        body: "Embodied carbon, a U-value, an end of life.",
        cta: "Ask us",
        hashtag: "#LCA",
      },
      image: null,
      suggested_keywords: [],
      accent_hex: null,
    },
    is_example: true,
  }),
  makeGeneration({
    id: "ex-post",
    workspace_id: "demo-ws",
    type: "post_pack",
    brief: "A LinkedIn post and a quote card on mycelium acoustic panels.",
    output: {
      post_text: "Reverberation time dropped from 1.4s to 0.6s.",
      hashtags: [],
      char_count: 45,
      card: {
        template_id: "quote",
        fields: {
          eyebrow: "Halden studio",
          headline: "First acoustic product I haven't had to hide.",
          body: "The project architect.",
          cta: "Read the field notes",
          hashtag: "#Mycelium",
        },
        image: null,
        suggested_keywords: [],
        accent_hex: null,
      },
    },
    is_example: true,
  }),
  makeGeneration({
    id: "ex-doc",
    workspace_id: "demo-ws",
    type: "document",
    brief: "A one-pager on the cost of a bio-based envelope.",
    output: {
      document: {
        archetype: "one-pager",
        title: "Bio-based envelopes, costed honestly",
        eyebrow: "Specifier brief",
        lede: "Where the premium comes from.",
        sections: [{ heading: "What the premium is", body: "5 to 12%.", bullets: [] }],
        footer: "Verdure Materials",
      },
      formats: { docx: { storage_key: "k.docx" }, pdf: { storage_key: "k.pdf" } },
    },
    is_example: true,
  }),
];

export const EXAMPLES: ExamplesResponse = {
  workspace_name: "Verdure Materials",
  brand: {
    colors: [
      { name: "Forest", hex: "#1C3A2E", role: "primary" },
      { name: "Ochre", hex: "#C98A3D", role: "accent" },
    ],
    fonts: { heading: null, body: null, mono: null },
    accent_hex: null,
    voice_summary: "Plainspoken and evidence-first.",
  },
  items: EXAMPLE_ITEMS,
};

/** One handler set typed against the client's OWN types — the contract-fidelity
 *  guard the audit (TEST-02) asked for: a FastAPI response-shape drift breaks these
 *  the same way BUILD-01's BrandProfile drift would have. Flow tests override
 *  individual routes with `server.use(...)`. */
export const handlers = [
  // A development server: live AI on, Cloudflare's always-pass test site key, password sign-in open.
  http.get("*/api/status", () =>
    HttpResponse.json<AppStatus>({
      live_ai_available: true,
      live_ai_reason: "available",
      turnstile_site_key: "1x00000000000000000000AA",
      password_login: true,
    }),
  ),

  http.post("*/api/auth/demo-login", () =>
    HttpResponse.json({ access_token: "demo-token", token_type: "bearer", expires_in: 86400 }),
  ),

  http.post("*/api/auth/login", () =>
    HttpResponse.json({ access_token: "test-token", token_type: "bearer", expires_in: 3600 }),
  ),

  http.get("*/api/auth/me", () =>
    HttpResponse.json<AuthUser>({
      id: "u1",
      email: "owner@example.com",
      full_name: "Owner",
      is_demo: false,
    }),
  ),

  // The public examples (no sign-in) and an example document's file.
  http.get("*/api/examples", () => HttpResponse.json<ExamplesResponse>(EXAMPLES)),
  http.get(
    "*/api/examples/:generationId/download/:fmt",
    () =>
      new HttpResponse(new Blob(["%PDF-1.7"]), { headers: { "Content-Type": "application/pdf" } }),
  ),

  // A generation whose id encodes the workspace, so a workspace switch is observable.
  http.get("*/api/workspaces/:workspaceId/generations", ({ params }) => {
    const id = String(params.workspaceId);
    return HttpResponse.json<GenerationPage>({
      items: [makeGeneration({ id: `gen-${id}`, workspace_id: id })],
      next_offset: null,
    });
  }),
];
