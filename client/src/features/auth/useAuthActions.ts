import { useState } from "react";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiError";
import { useAuthStore, type AuthUser } from "@/stores/auth";

type Pending = "demo" | "password" | null;

/** Demo + password sign-in. The session is stored only once /auth/me returns the user. */
export function useAuthActions() {
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

  async function loginDemo() {
    setError(null);
    setPending("demo");
    try {
      const res = await api.post<{ access_token: string }>("/auth/demo-login");
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
