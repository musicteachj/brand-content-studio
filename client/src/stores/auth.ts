import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  is_demo: boolean;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  /** Token and user land together, so a reload can never find one without the other. */
  setSession: (token: string, user: AuthUser) => void;
  logout: () => void;
}

type PersistedAuth = Pick<AuthState, "token" | "user">;

function isAuthUser(value: unknown): value is AuthUser {
  const u = value as Partial<AuthUser> | null;
  return (
    typeof u === "object" &&
    u !== null &&
    typeof u.id === "string" &&
    typeof u.email === "string" &&
    typeof u.full_name === "string" &&
    typeof u.is_demo === "boolean"
  );
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      setSession: (token, user) => set({ token, user, isAuthenticated: true }),
      logout: () => set({ token: null, user: null, isAuthenticated: false }),
    }),
    {
      name: "folio-auth",
      partialize: (s): PersistedAuth => ({ token: s.token, user: s.user }),
      // A stored session missing its token or a well-formed user (e.g. saved by an
      // older build mid sign-in) counts as signed out, so it can't show owner
      // controls (QA-02).
      merge: (persisted, current) => {
        const { token, user } = (persisted ?? {}) as Partial<Record<keyof PersistedAuth, unknown>>;
        return typeof token === "string" && token && isAuthUser(user)
          ? { ...current, token, user, isAuthenticated: true }
          : { ...current, token: null, user: null, isAuthenticated: false };
      },
    },
  ),
);
