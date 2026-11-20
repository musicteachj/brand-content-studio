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

export const appStatusQuery = {
  queryKey: ["app-status"],
  queryFn: async () => (await api.get<AppStatus>("/status")).data,
  staleTime: 30_000,
};

export function useAppStatus() {
  return useQuery(appStatusQuery);
}
