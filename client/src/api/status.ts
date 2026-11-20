import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/** GET /api/status: public, no sign-in. The server caches the live-AI answer for 30 s. */
export interface AppStatus {
  live_ai_available: boolean;
  live_ai_reason: "available" | "off" | "paused";
  /** The Turnstile site key for the demo start (Cloudflare's test key in development). */
  turnstile_site_key: string;
  /** False in production, where the demo is the only way in. */
  password_login: boolean;
}

/** The server's LIVE_AI_PAUSED_COPY (server/app/utils/errors.py), shown on the start page
 *  before a visitor starts a demo while live generation is off or paused. */
export const LIVE_AI_PAUSED_COPY =
  "Live generation is paused right now. Browse the ready-made examples to see what Folio makes.";

/** The server's DEMO_ENDED_COPY, shown on the start page after a demo session's 401. */
export const DEMO_ENDED_COPY = "Your demo session ended. Start a new one any time.";

export const appStatusQuery = {
  queryKey: ["app-status"],
  queryFn: async () => (await api.get<AppStatus>("/status")).data,
  staleTime: 30_000,
};

export function useAppStatus() {
  return useQuery(appStatusQuery);
}
