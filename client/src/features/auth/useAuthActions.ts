import { useState } from "react";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/apiError";
import { useAuthStore, type AuthUser } from "@/stores/auth";

type Pending = "demo" | "password" | null;

/** Demo + password sign-in. Token is set before /auth/me so the interceptor attaches it. */
export function useAuthActions() {
  const setToken = useAuthStore((s) => s.setToken);
  const setUser = useAuthStore((s) => s.setUser);
  const [pending, setPending] = useState<Pending>(null);
  const [error, setError] = useState<string | null>(null);

  async function finish(token: string) {
    // Token must be set first so the interceptor authenticates /auth/me. If that
    // call fails, roll back so we never persist a half-authenticated state
    // (isAuthenticated=true with user=null) that would survive a reload.
    setToken(token);
    try {
      const me = await api.get<AuthUser>("/auth/me");
      setUser(me.data);
    } catch (err) {
      useAuthStore.getState().logout();
      throw err;
    }
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
