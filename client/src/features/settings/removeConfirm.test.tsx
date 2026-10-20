import type { ComponentType } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { useWorkspaces } from "@/api/workspaces";
import { useAuthStore } from "@/stores/auth";
import { makeBrandProfile } from "@/test/factories";
import { setupMswServer } from "@/test/msw/lifecycle";
import { server } from "@/test/msw/server";
import type { BrandProfile, Workspace } from "@/types";
import { BrandFontsSection } from "./BrandFontsSection";
import { BrandImagesSection } from "./BrandImagesSection";
import { CardPresetsSection } from "./CardPresetsSection";
import { ExemplarsSection } from "./ExemplarsSection";

setupMswServer();

// Same gap QA-04 closed for assets, workspaces, templates, and History: these four
// brand-profile items were removed on one click, with no way back.

const WORKSPACE = {
  id: "ws1",
  name: "QA",
  brand_profile: makeBrandProfile({
    brand_images: [{ id: "img1", storage_key: "k1", url: null, name: "Hero shot" }],
    exemplars: [{ id: "ex1", storage_key: "k2", url: null, style_note: "Bold, short lines." }],
    uploaded_fonts: [{ id: "font1", family: "Acme Sans", storage_key: "k3", url: null }],
    card_presets: [{ id: "pre1", name: "Bold quote", template_id: "quote", accent_hex: null }],
  }),
} as unknown as Workspace;

const SECTIONS: {
  label: string;
  Section: ComponentType<{ workspace: Workspace }>;
  path: string;
  field: "brand_images" | "exemplars" | "uploaded_fonts" | "card_presets";
  id: string;
  trigger: string;
  dialog: string;
  confirm: string;
  eyebrow: RegExp;
}[] = [
  {
    label: "a brand image",
    Section: BrandImagesSection,
    path: "brand-images",
    field: "brand_images",
    id: "img1",
    trigger: "Remove Hero shot",
    dialog: "Remove “Hero shot”?",
    confirm: "Remove image",
    eyebrow: /^Brand images ·/,
  },
  {
    label: "an example card",
    Section: ExemplarsSection,
    path: "exemplars",
    field: "exemplars",
    id: "ex1",
    trigger: "Remove example card",
    dialog: "Remove this example card?",
    confirm: "Remove example card",
    eyebrow: /^Example cards ·/,
  },
  {
    label: "an uploaded font",
    Section: BrandFontsSection,
    path: "fonts",
    field: "uploaded_fonts",
    id: "font1",
    trigger: "Remove Acme Sans",
    dialog: "Remove “Acme Sans”?",
    confirm: "Remove font",
    eyebrow: /^Brand fonts ·/,
  },
  {
    label: "a card preset",
    Section: CardPresetsSection,
    path: "card-presets",
    field: "card_presets",
    id: "pre1",
    trigger: "Remove Bold quote",
    dialog: "Remove “Bold quote”?",
    confirm: "Remove preset",
    eyebrow: /^Card presets ·/,
  },
];

function signIn(isDemo: boolean) {
  useAuthStore.setState({
    token: "t",
    isAuthenticated: true,
    user: { id: "u1", email: "owner@example.com", full_name: "Owner", is_demo: isDemo },
  });
}

/** Renders the section from the workspaces query, as Settings does, so a remove
 *  really takes the row (and the dialog inside it) away once the list refetches. */
function renderSection(Section: ComponentType<{ workspace: Workspace }>) {
  function Host() {
    const { data } = useWorkspaces();
    return data ? <Section workspace={data[0]} /> : null;
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Host />
    </QueryClientProvider>,
  );
}

/** Serves the workspace and records every DELETE the section sends. A successful
 *  one removes the item from what the next fetch returns; `status` makes it fail. */
function serveWorkspace(s: { path: string; field: keyof BrandProfile }, status = 200) {
  let workspace = WORKSPACE;
  const deleted: string[] = [];
  server.use(
    http.get("*/api/workspaces", () => HttpResponse.json([workspace])),
    http.delete(`*/api/workspaces/ws1/${s.path}/:id`, ({ params }) => {
      deleted.push(String(params.id));
      if (status !== 200) return HttpResponse.json({ detail: "Storage is down." }, { status });
      const items = workspace.brand_profile[s.field] as { id: string }[];
      workspace = {
        ...workspace,
        brand_profile: {
          ...workspace.brand_profile,
          [s.field]: items.filter((item) => item.id !== params.id),
        },
      };
      return HttpResponse.json(workspace);
    }),
  );
  return deleted;
}

beforeEach(() => signIn(false));

describe.each(SECTIONS)("removing $label", (s) => {
  it("asks first, and Cancel removes nothing and returns focus", async () => {
    const deleted = serveWorkspace(s);
    renderSection(s.Section);

    const trigger = await screen.findByRole("button", { name: s.trigger });
    await userEvent.click(trigger);
    expect(await screen.findByRole("dialog", { name: s.dialog })).toBeInTheDocument();
    expect(deleted).toEqual([]);

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deleted).toEqual([]);
    expect(trigger).toHaveFocus();
  });

  it("removes on confirm, then focuses the section's count", async () => {
    const deleted = serveWorkspace(s);
    renderSection(s.Section);

    await userEvent.click(await screen.findByRole("button", { name: s.trigger }));
    await userEvent.click(await screen.findByRole("button", { name: s.confirm }));
    await waitFor(() => expect(deleted).toEqual([s.id]));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // The row (with the dialog's trigger) goes once the list refetches, so focus
    // lands on the count, which stays, instead of dropping to <body>.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: s.trigger })).not.toBeInTheDocument(),
    );
    expect(screen.getByText(s.eyebrow)).toHaveFocus();
  });

  it("keeps the dialog open with the server's reason when the remove fails", async () => {
    serveWorkspace(s, 500);
    renderSection(s.Section);

    await userEvent.click(await screen.findByRole("button", { name: s.trigger }));
    await userEvent.click(await screen.findByRole("button", { name: s.confirm }));
    const dialog = screen.getByRole("dialog", { name: s.dialog });
    expect(await screen.findByRole("alert")).toHaveTextContent("Storage is down.");
    expect(dialog).toBeInTheDocument();
  });
});

describe("the demo user", () => {
  it("gets no remove controls, and the example card's is disabled", async () => {
    signIn(true);
    server.use(http.get("*/api/workspaces", () => HttpResponse.json([WORKSPACE])));
    for (const s of SECTIONS) renderSection(s.Section);
    await screen.findByText(/^Card presets ·/);

    expect(screen.queryByRole("button", { name: "Remove Hero shot" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove Acme Sans" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove Bold quote" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove example card" })).toBeDisabled();
  });
});
