import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeBrandProfile } from "@/test/factories";
import type { Workspace } from "@/types";
import { BrandFontsSection } from "./BrandFontsSection";

// QA-03 / QA-12 / QA-15: the server says exactly what's wrong with an upload; the
// page used to replace it with a generic guess, and didn't announce it.
//
// The upload hook is mocked rather than served through MSW: on Node 20 (CI), an
// axios FormData request through jsdom's XHR never settles when MSW answers with
// an HTTP error, so the test could only time out. apiErrorMessage's own tests
// cover reading the detail off a real AxiosError.
// A plain function, not vi.fn(): with vitest 2.1, a vi.fn whose implementation
// rejects failed the test with that rejection even though the component handles
// it (every assertion passed first).
let uploadError: unknown;
const uploadCalls: unknown[] = [];
function addFont(args: unknown): Promise<never> {
  uploadCalls.push(args);
  return Promise.reject(uploadError);
}
vi.mock("@/api/workspaces", () => ({
  useAddFont: () => ({ mutateAsync: addFont, isPending: false }),
  useRemoveFont: () => ({ mutate: vi.fn(), isPending: false }),
}));

function axiosError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError("Request failed", "ERR_BAD_REQUEST", config, null, {
    status,
    statusText: "",
    headers: {},
    config,
    data,
  });
}

const WORKSPACE = {
  id: "ws1",
  name: "QA",
  brand_profile: makeBrandProfile({ uploaded_fonts: [] }),
} as unknown as Workspace;

async function uploadFont(name: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { container } = render(
    <QueryClientProvider client={qc}>
      <BrandFontsSection workspace={WORKSPACE} />
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByPlaceholderText(/Font name/), name);
  const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
  await userEvent.upload(input, new File(["x"], "font.ttf", { type: "font/ttf" }));
}

beforeEach(() => {
  uploadError = undefined;
  uploadCalls.length = 0;
});

describe("upload errors show the server's reason", () => {
  it("announces the server's detail instead of a generic message", async () => {
    uploadError = axiosError(400, {
      detail: "Font name may use letters, numbers, spaces, and . _ - only.",
    });
    await uploadFont("Söhne");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Font name may use letters, numbers, spaces, and . _ - only.",
    );
    expect(uploadCalls).toEqual([expect.objectContaining({ name: "Söhne" })]);
  });

  it("keeps the helpful fallback when the server gives no reason", async () => {
    uploadError = new AxiosError("Network Error", "ERR_NETWORK");
    await uploadFont("Acme Sans");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Upload a \.ttf under 5 MB/);
  });
});
