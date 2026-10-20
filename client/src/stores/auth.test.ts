import { beforeEach, describe, expect, it } from "vitest";
import { useAuthStore } from "@/stores/auth";

const user = { id: "u1", email: "owner@example.com", full_name: "Owner", is_demo: false };

function persisted(state: Record<string, unknown>) {
  localStorage.setItem("folio-auth", JSON.stringify({ state, version: 0 }));
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.getState().logout();
});

describe("auth store rehydration", () => {
  // QA-02: browsers already holding the half session must recover on load.
  it("drops a persisted session that has a token but no user", async () => {
    persisted({ token: "t", user: null, isAuthenticated: true });
    await useAuthStore.persist.rehydrate();

    const s = useAuthStore.getState();
    expect(s.isAuthenticated).toBe(false);
    expect(s.token).toBeNull();
    expect(s.user).toBeNull();
  });

  it("drops a persisted user with no token", async () => {
    persisted({ token: null, user, isAuthenticated: true });
    await useAuthStore.persist.rehydrate();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("drops a persisted user that isn't a well-formed user", async () => {
    persisted({ token: "t", user: { id: "u1" }, isAuthenticated: true });
    await useAuthStore.persist.rehydrate();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("restores a complete session", async () => {
    persisted({ token: "t", user, isAuthenticated: true });
    await useAuthStore.persist.rehydrate();

    const s = useAuthStore.getState();
    expect(s.isAuthenticated).toBe(true);
    expect(s.token).toBe("t");
    expect(s.user).toEqual(user);
  });
});
