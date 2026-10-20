import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import { describe, expect, it } from "vitest";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "./ConfirmDialog";

function setup(onConfirm: () => Promise<void>) {
  render(
    <ConfirmDialog
      trigger={<Button aria-label="Delete notes.md">Delete</Button>}
      title="Delete “notes.md”?"
      description="This removes the file and its retrievable chunks."
      confirmLabel="Delete asset"
      onConfirm={onConfirm}
      errorFallback="Couldn’t delete. Try again."
    />,
  );
  return screen.getByRole("button", { name: "Delete notes.md" });
}

describe("ConfirmDialog", () => {
  it("does nothing until confirmed, and Cancel returns focus to the trigger", async () => {
    let calls = 0;
    const trigger = setup(async () => {
      calls += 1;
    });
    await userEvent.click(trigger);
    expect(await screen.findByRole("dialog", { name: "Delete “notes.md”?" })).toBeInTheDocument();
    expect(calls).toBe(0);

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls).toBe(0);
    expect(trigger).toHaveFocus();
  });

  it("runs the action on confirm and closes", async () => {
    let calls = 0;
    const trigger = setup(async () => {
      calls += 1;
    });
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole("button", { name: "Delete asset" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls).toBe(1);
  });

  it("stays open with an alert when the action fails", async () => {
    const trigger = setup(() => Promise.reject(new Error("offline")));
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole("button", { name: "Delete asset" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn’t delete. Try again.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

function WithFallback({ onConfirm }: { onConfirm: () => Promise<void> }) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  return (
    <>
      <h2 ref={headingRef} tabIndex={-1}>
        Assets
      </h2>
      <ConfirmDialog
        trigger={<Button aria-label="Delete notes.md">Delete</Button>}
        title="Delete “notes.md”?"
        description="Gone for good."
        confirmLabel="Delete asset"
        onConfirm={onConfirm}
        errorFallback="Couldn’t delete. Try again."
        focusAfterConfirm={headingRef}
      />
    </>
  );
}

describe("ConfirmDialog focus and pending", () => {
  it("moves focus to focusAfterConfirm once the action succeeds", async () => {
    render(<WithFallback onConfirm={async () => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Delete notes.md" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete asset" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Assets" })).toHaveFocus();
  });

  it("can't be dismissed while the action is in flight", async () => {
    let finish!: () => void;
    render(<WithFallback onConfirm={() => new Promise<void>((r) => (finish = r))} />);
    await userEvent.click(screen.getByRole("button", { name: "Delete notes.md" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete asset" }));

    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();

    finish();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
