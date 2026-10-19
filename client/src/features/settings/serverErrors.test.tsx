import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { makeBrandProfile } from "@/test/factories";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";
import type { Workspace } from "@/types";
import { BrandFontsSection } from "./BrandFontsSection";

setupMswServer();

// QA-03 / QA-12 / QA-15: the server says exactly what's wrong with an upload; the
// page used to replace it with a generic guess, and didn't announce it.
const WORKSPACE = {
  id: "ws1",
  name: "QA",
  brand_profile: makeBrandProfile({ uploaded_fonts: [] }),
} as unknown as Workspace;

function renderFonts() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <BrandFontsSection workspace={WORKSPACE} />
    </QueryClientProvider>,
  );
}

describe("upload errors show the server's reason", () => {
  it("announces the server's detail instead of a generic message", async () => {
    server.use(
      http.post("*/api/workspaces/ws1/fonts", () =>
        HttpResponse.json(
          { detail: "Font name may use letters, numbers, spaces, and . _ - only." },
          { status: 400 },
        ),
      ),
    );
    const { container } = renderFonts();
    await userEvent.type(screen.getByPlaceholderText(/Font name/), "Söhne");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(input, new File(["x"], "sohne.ttf", { type: "font/ttf" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Font name may use letters, numbers, spaces, and . _ - only.",
    );
  });

  it("keeps the helpful fallback when the server gives no reason", async () => {
    server.use(http.post("*/api/workspaces/ws1/fonts", () => HttpResponse.error()));
    const { container } = renderFonts();
    await userEvent.type(screen.getByPlaceholderText(/Font name/), "Acme Sans");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(input, new File(["x"], "acme.ttf", { type: "font/ttf" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Upload a \.ttf under 5 MB/);
  });
});
