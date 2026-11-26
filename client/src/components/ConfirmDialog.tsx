import { useRef, useState, type ReactElement, type RefObject } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Button } from "@/components/ui/button";
import { apiErrorMessage } from "@/lib/apiError";

/** A confirm step for destructive actions. `trigger` opens it (as a Radix Trigger,
 *  so focus returns to it on Cancel); the dialog stays open with an alert if
 *  `onConfirm` fails, and closes once it succeeds. When the confirmed action
 *  removes the trigger itself (deleting its row), pass `focusAfterConfirm` so
 *  focus lands somewhere that survives instead of dropping to <body>. */
export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel,
  onConfirm,
  errorFallback,
  focusAfterConfirm,
}: {
  trigger: ReactElement;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => Promise<void>;
  errorFallback: string;
  focusAfterConfirm?: RefObject<HTMLElement | null>;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirmedRef = useRef(false);

  async function confirm() {
    setPending(true);
    setError(null);
    try {
      await onConfirm();
      confirmedRef.current = true;
      setOpen(false);
    } catch (err) {
      setError(apiErrorMessage(err, errorFallback));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (pending) return; // stay open until the action settles, so its result is seen
        setOpen(next);
        setError(null);
        if (next) confirmedRef.current = false;
      }}
    >
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-modal bg-foreground/30 backdrop-blur-[1px]" />
        <Dialog.Content
          onCloseAutoFocus={(e) => {
            const target = focusAfterConfirm?.current;
            if (confirmedRef.current && target) {
              e.preventDefault();
              target.focus();
            }
          }}
          className="fixed left-1/2 top-1/2 z-modal flex w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-xl border border-border bg-surface p-6 shadow-heavy"
        >
          <Dialog.Title className="text-base font-semibold text-foreground">{title}</Dialog.Title>
          <Dialog.Description className="text-sm text-muted-foreground">
            {description}
          </Dialog.Description>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Dialog.Close asChild>
              <Button variant="secondary" size="sm" disabled={pending}>
                Cancel
              </Button>
            </Dialog.Close>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void confirm()}
              loading={pending}
            >
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
