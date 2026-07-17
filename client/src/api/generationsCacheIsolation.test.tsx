import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useGenerations } from "@/api/generations";
import { setupMswServer } from "@/test/msw/lifecycle";

setupMswServer();

// Renders just the generation ids for a workspace — enough to observe which
// workspace's list is on screen. The default MSW handler returns `gen-<workspaceId>`.
function Harness({ workspaceId }: { workspaceId: string }) {
  const q = useGenerations(workspaceId);
  const ids = q.data?.pages.flatMap((p) => p.items).map((g) => g.id) ?? [];
  return (
    <ul>
      {ids.map((id) => (
        <li key={id}>{id}</li>
      ))}
    </ul>
  );
}

describe("generations cache isolation on workspace switch", () => {
  it("switching workspace refetches — workspace A's generations don't render under B", async () => {
    // One shared client across the switch: if the query key dropped workspaceId,
    // B would read A's cached page and this test would fail.
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrap = (workspaceId: string) => (
      <QueryClientProvider client={qc}>
        <Harness workspaceId={workspaceId} />
      </QueryClientProvider>
    );

    const { rerender } = render(wrap("ws-A"));
    await waitFor(() => expect(screen.getByText("gen-ws-A")).toBeInTheDocument());

    rerender(wrap("ws-B"));
    await waitFor(() => expect(screen.getByText("gen-ws-B")).toBeInTheDocument());
    expect(screen.queryByText("gen-ws-A")).not.toBeInTheDocument();
  });
});
