import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { setupMswServer } from "@/test/msw/lifecycle";
import { useAuthStore } from "@/stores/auth";
import { SideNav } from "./SideNav";

// The app is desktop-first (DECISIONS #39). Below the `lg` breakpoint the sidebar
// starts collapsed, so a narrow window or tablet keeps room for the page.

setupMswServer();

type Listener = (e: { matches: boolean }) => void;

/** Stub matchMedia with a "narrow" answer the test controls (and can change). */
function stubViewport(narrow: boolean) {
  const listeners = new Set<Listener>();
  vi.stubGlobal("matchMedia", (media: string) => ({
    get matches() {
      return narrow;
    },
    media,
    addEventListener: (_: string, l: Listener) => listeners.add(l),
    removeEventListener: (_: string, l: Listener) => listeners.delete(l),
  }));
  return {
    resize(nowNarrow: boolean) {
      narrow = nowNarrow;
      act(() => listeners.forEach((l) => l({ matches: nowNarrow })));
    },
  };
}

function renderNav() {
  render(
    <MemoryRouter>
      <SideNav />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useAuthStore.setState({
    token: "t",
    isAuthenticated: true,
    user: { id: "u1", email: "owner@example.com", full_name: "Owner", is_demo: false },
  });
});

afterEach(() => vi.unstubAllGlobals());

describe("SideNav width", () => {
  it("starts expanded on a wide screen", () => {
    stubViewport(false);
    renderNav();
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("starts collapsed on a narrow screen, and can still be expanded", async () => {
    stubViewport(true);
    renderNav();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
    // Collapsed links keep their name (the title), so they stay usable.
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("keeps Sign out when collapsed", async () => {
    const logout = vi.fn();
    useAuthStore.setState({ logout });
    stubViewport(true);
    renderNav();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(logout).toHaveBeenCalledOnce();
  });

  it("asks before a demo visitor signs out, and ends the session on the server first", async () => {
    const order: string[] = [];
    const logout = vi.fn(() => {
      order.push("logout");
    });
    server.use(
      http.post("/api/auth/end-demo", () => {
        order.push("end-demo");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    useAuthStore.setState({
      logout,
      user: { id: "d1", email: "d@x.io", full_name: "Demo", is_demo: true },
    });
    stubViewport(false);
    renderNav();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(logout).not.toHaveBeenCalled();
    expect(order).toEqual([]);
    expect(await screen.findByRole("dialog", { name: "End your demo?" })).toHaveTextContent(
      "Signing out ends this demo. Your work stays private and is removed after 24 hours.",
    );
    await userEvent.click(screen.getByRole("button", { name: "End demo" }));
    await waitFor(() => expect(logout).toHaveBeenCalledOnce());
    expect(order).toEqual(["end-demo", "logout"]);
  });

  it("signs a demo visitor out locally even when the end-demo call fails", async () => {
    const logout = vi.fn();
    server.use(http.post("/api/auth/end-demo", () => new HttpResponse(null, { status: 500 })));
    useAuthStore.setState({
      logout,
      user: { id: "d1", email: "d@x.io", full_name: "Demo", is_demo: true },
    });
    stubViewport(false);
    renderNav();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await userEvent.click(await screen.findByRole("button", { name: "End demo" }));
    await waitFor(() => expect(logout).toHaveBeenCalledOnce());
  });

  it("follows the window across the breakpoint", () => {
    const viewport = stubViewport(false);
    renderNav();

    viewport.resize(true);
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();

    viewport.resize(false);
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
  });
});
