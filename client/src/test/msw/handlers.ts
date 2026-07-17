import { http, HttpResponse } from "msw";
import type { AuthUser } from "@/stores/auth";
import { makeGeneration } from "@/test/factories";
import type { GenerationPage } from "@/types";

/** One handler set typed against the client's OWN types — the contract-fidelity
 *  guard the audit (TEST-02) asked for: a FastAPI response-shape drift breaks these
 *  the same way BUILD-01's BrandProfile drift would have. Flow tests override
 *  individual routes with `server.use(...)`. */
export const handlers = [
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

  // A generation whose id encodes the workspace, so a workspace switch is observable.
  http.get("*/api/workspaces/:workspaceId/generations", ({ params }) => {
    const id = String(params.workspaceId);
    return HttpResponse.json<GenerationPage>({
      items: [makeGeneration({ id: `gen-${id}`, workspace_id: id })],
      next_offset: null,
    });
  }),
];
