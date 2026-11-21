import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";

setupMswServer();

const demoUser = { id: "d1", email: "demo@folio.studio", full_name: "Demo", is_demo: true };
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

describe("a 401 ends the demo", () => {
  it("logs a demo visitor out with the ended reason, which is not persisted", async () => {
    useAuthStore.getState().setSession("t", demoUser);
    server.use(http.get("*/api/ping", () => HttpResponse.json({ detail: "x" }, { status: 401 })));
    await expect(api.get("/ping")).rejects.toBeTruthy();

    const s = useAuthStore.getState();
    expect(s.isAuthenticated).toBe(false);
    expect(s.endedReason).toBe("ended");
    expect(JSON.parse(localStorage.getItem("folio-auth")!).state.endedReason).toBeUndefined();
  });

  it("signs an owner out without the ended reason", async () => {
    useAuthStore.getState().setSession("t", user);
    server.use(http.get("*/api/ping", () => HttpResponse.json({ detail: "x" }, { status: 401 })));
    await expect(api.get("/ping")).rejects.toBeTruthy();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().endedReason).toBeNull();
  });

  it("keeps the ended reason through a burst of 401s", async () => {
    useAuthStore.getState().setSession("t", demoUser);
    server.use(http.get("*/api/ping", () => HttpResponse.json({ detail: "x" }, { status: 401 })));
    await Promise.allSettled([api.get("/ping"), api.get("/ping")]);
    await expect(api.get("/ping")).rejects.toBeTruthy();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().endedReason).toBe("ended");
  });

  it("clears the reason when a new session starts", () => {
    useAuthStore.getState().logout("ended");
    useAuthStore.getState().setSession("t", demoUser);
    expect(useAuthStore.getState().endedReason).toBeNull();
  });
});
