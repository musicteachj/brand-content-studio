import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { api } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";
import { endSessionOn401, useAuthStore } from "@/stores/auth";
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
  queryClient.clear();
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

// These pass only because the interceptor reads the Bearer token from the failed request:
// the "logs a demo visitor out with the ended reason" and "signs an owner out without the
// ended reason" interceptor tests above prove that read works, since a broken read would give
// null and leave every session signed in.
describe("a stale 401", () => {
  it("leaves a newer session signed in when the failed request carried an old token", async () => {
    useAuthStore.getState().setSession("old", demoUser);
    server.use(
      http.get("*/api/ping", () => {
        // The visitor starts a new session while this request is in flight.
        useAuthStore.getState().setSession("new", demoUser);
        return HttpResponse.json({ detail: "x" }, { status: 401 });
      }),
    );
    await expect(api.get("/ping")).rejects.toBeTruthy();

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().token).toBe("new");
  });

  it("endSessionOn401 ignores a token that is not the current one", () => {
    useAuthStore.getState().setSession("new", demoUser);
    endSessionOn401("old");
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    endSessionOn401(null);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it("still signs out, with the ended reason, when the 401 carried the current token", () => {
    useAuthStore.getState().setSession("cur", demoUser);
    endSessionOn401("cur");
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().endedReason).toBe("ended");
  });
});

describe("the query cache follows the session", () => {
  const key = ["generations", "ws-demo"];

  it("is emptied by logout, so the next session never sees the last one's data", () => {
    useAuthStore.getState().setSession("a", demoUser);
    queryClient.setQueryData(key, [{ id: "from-session-a" }]);
    useAuthStore.getState().logout();
    expect(queryClient.getQueryData(key)).toBeUndefined();

    useAuthStore.getState().setSession("b", demoUser);
    expect(queryClient.getQueryData(key)).toBeUndefined();
  });

  it("is emptied when a new session starts through setSession", () => {
    useAuthStore.getState().setSession("a", demoUser);
    queryClient.setQueryData(key, [{ id: "from-session-a" }]);
    useAuthStore.getState().setSession("b", demoUser);
    expect(queryClient.getQueryData(key)).toBeUndefined();
  });

  it("is emptied by a 401 sign-out", () => {
    useAuthStore.getState().setSession("a", demoUser);
    queryClient.setQueryData(key, [{ id: "from-session-a" }]);
    endSessionOn401("a");
    expect(queryClient.getQueryData(key)).toBeUndefined();
  });
});

describe("a mounted consumer follows the session", () => {
  function History() {
    const { data } = useQuery({
      queryKey: ["generations", "ws-demo"],
      queryFn: async () => `history-of-${useAuthStore.getState().token}`,
    });
    return <p>{data ?? "loading"}</p>;
  }

  it("stops rendering the old session's data once the token changes", async () => {
    useAuthStore.getState().setSession("a", demoUser);
    render(
      <QueryClientProvider client={queryClient}>
        <History />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("history-of-a")).toBeInTheDocument();

    act(() => useAuthStore.getState().setSession("b", demoUser));
    await waitFor(() => expect(screen.getByText("history-of-b")).toBeInTheDocument());
    expect(screen.queryByText("history-of-a")).not.toBeInTheDocument();
  });
});
