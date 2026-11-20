import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { appStatusQuery } from "@/api/status";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiError";
import { getTurnstileToken } from "@/lib/turnstile";
import { useAuthStore, type AuthUser } from "@/stores/auth";

type Pending = "demo" | "password" | null;

/** Demo + password sign-in. The session is stored only once /auth/me returns the user. */
export function useAuthActions() {
  const queryClient = useQueryClient();
  const setSession = useAuthStore((s) => s.setSession);
  const [pending, setPending] = useState<Pending>(null);
  const [error, setError] = useState<string | null>(null);

  async function finish(token: string) {
    // Nothing is stored until the user is loaded: a reload mid-request must not
    // find a session with no user, which would show a demo visitor owner
    // controls (QA-02). The store has no token yet, so pass it explicitly.
    const me = await api.get<AuthUser>("/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    setSession(token, me.data);
  }

  /** A Turnstile token for this start, or "" when none could be had (the script didn't load,
   *  the check failed): the server then refuses in its own words, which are shown. */
  async function turnstileToken(slot: HTMLElement | null): Promise<string> {
    if (!slot) return "";
    try {
      const status = await queryClient.fetchQuery(appStatusQuery);
      return await getTurnstileToken(slot, status.turnstile_site_key);
    } catch {
      return "";
    }
  }

  /** "Explore as demo": a bot check in `slot`, then a new visitor session. */
  async function loginDemo(slot: HTMLElement | null) {
    setError(null);
    setPending("demo");
    try {
      const turnstile_token = await turnstileToken(slot);
      const res = await api.post<{ access_token: string }>("/auth/demo-login", { turnstile_token });
      await finish(res.data.access_token);
    } catch (err) {
      setError(apiErrorMessage(err, "Demo sign-in failed. Is the server running and seeded?"));
      throw err;
    } finally {
      setPending(null);
    }
  }

  async function loginPassword(email: string, password: string) {
    setError(null);
    setPending("password");
    try {
      const res = await api.post<{ access_token: string }>("/auth/login", { email, password });
      await finish(res.data.access_token);
    } catch (err) {
      setError(apiErrorMessage(err, "Incorrect email or password."));
      throw err;
    } finally {
      setPending(null);
    }
  }

  return { loginDemo, loginPassword, pending, error };
}
