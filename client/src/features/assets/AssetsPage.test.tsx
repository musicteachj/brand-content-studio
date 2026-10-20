import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";
import type { Asset, AssetPage } from "@/types";
import { AssetsPage } from "./AssetsPage";

vi.mock("@/features/workspace/useActiveWorkspace", () => ({
  useActiveWorkspace: () => ({ workspace: { id: "ws1" }, workspaceId: "ws1" }),
}));

setupMswServer();

const ASSET: Asset = {
  id: "a1",
  workspace_id: "ws1",
  filename: "voice-and-tone.pdf",
  content_type: "application/pdf",
  asset_kind: "voice",
  size_bytes: 5120,
  ingestion_status: "ready",
  chunk_count: 6,
  error: null,
  ingested_at: null,
  created_at: null,
  updated_at: null,
};

beforeEach(() => {
  useAuthStore.setState({
    token: "t",
    isAuthenticated: true,
    user: { id: "u1", email: "owner@example.com", full_name: "Owner", is_demo: false },
  });
});

// QA-04: the trash icon deleted the file and its vectors on one click.
describe("AssetsPage delete", () => {
  it("asks before deleting, and deletes only on confirm", async () => {
    const deleted: string[] = [];
    server.use(
      http.get("*/api/workspaces/ws1/assets", () =>
        HttpResponse.json<AssetPage>({ items: [ASSET], next_offset: null }),
      ),
      http.delete("*/api/workspaces/ws1/assets/:id", ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AssetsPage />
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "Delete voice-and-tone.pdf" }));
    expect(
      await screen.findByRole("dialog", { name: "Delete “voice-and-tone.pdf”?" }),
    ).toBeInTheDocument();
    expect(deleted).toEqual([]);

    await userEvent.click(screen.getByRole("button", { name: "Delete asset" }));
    await waitFor(() => expect(deleted).toEqual(["a1"]));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // The row is going away, so focus lands on the list heading, not <body>.
    expect(screen.getByRole("heading", { name: /^Assets/ })).toHaveFocus();
  });
});
