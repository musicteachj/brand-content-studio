import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import App from "@/App";
import { useAuthStore } from "@/stores/auth";
import { setupMswServer } from "@/test/msw/lifecycle";

setupMswServer();

function renderPrivacy() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/privacy"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.getState().logout();
});

describe("PrivacyPage", () => {
  it("is reachable signed out", async () => {
    renderPrivacy();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Privacy and terms" }),
    ).toBeInTheDocument();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("states the retention and names every processor", async () => {
    renderPrivacy();
    await screen.findByRole("heading", { level: 1, name: "Privacy and terms" });
    expect(
      screen.getByText(
        /removed from the app after 24 hours; backups up to 7 days; server logs \(including IP addresses\) 14 days/,
      ),
    ).toBeInTheDocument();
    for (const name of ["Anthropic", "OpenAI", "Cloudflare", "Unsplash", "AWS", "MongoDB Atlas"]) {
      expect(screen.getByText(new RegExp(name))).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: /jameslittlefield\.net/ })).toHaveAttribute(
      "href",
      "https://jameslittlefield.net",
    );
  });
});
