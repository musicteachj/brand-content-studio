// QA-16: Generate's mode buttons didn't expose the selected mode, and Settings'
// only h1 was "Appearance" (one of its sections).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/features/workspace/useActiveWorkspace", () => ({
  useActiveWorkspace: () => ({ workspace: undefined, workspaceId: null }),
}));
// The modes and settings sections have their own tests; stub them to isolate the chrome.
vi.mock("@/features/generate/modes/TextMode", () => ({ TextMode: () => null }));
vi.mock("@/features/generate/modes/CardMode", () => ({ CardMode: () => null }));
vi.mock("@/features/generate/modes/PostPackMode", () => ({ PostPackMode: () => null }));
vi.mock("@/features/generate/modes/DocumentMode", () => ({ DocumentMode: () => null }));
vi.mock("@/features/settings/BrandIdentityEditor", () => ({ BrandIdentityEditor: () => null }));
vi.mock("@/features/settings/BrandFontsSection", () => ({ BrandFontsSection: () => null }));
vi.mock("@/features/settings/BrandImagesSection", () => ({ BrandImagesSection: () => null }));
vi.mock("@/features/settings/CardPresetsSection", () => ({ CardPresetsSection: () => null }));
vi.mock("@/features/settings/ExemplarsSection", () => ({ ExemplarsSection: () => null }));
vi.mock("@/features/settings/WorkspacesSection", () => ({ WorkspacesSection: () => null }));

import { GeneratePage } from "@/features/generate/GeneratePage";
import { SettingsPage } from "@/features/settings/SettingsPage";

describe("page chrome a11y", () => {
  it("Generate marks the selected mode with aria-pressed", async () => {
    render(<GeneratePage />);
    const text = screen.getByRole("button", { name: "Text post" });
    const card = screen.getByRole("button", { name: "Image card" });
    expect(text).toHaveAttribute("aria-pressed", "true");
    expect(card).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(card);
    expect(card).toHaveAttribute("aria-pressed", "true");
    expect(text).toHaveAttribute("aria-pressed", "false");
  });

  it("Settings has one page-level h1", () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s.map((h) => h.textContent)).toEqual(["Settings"]);
  });
});
