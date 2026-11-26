import { Lock } from "lucide-react";

/** Explains why controls are disabled for a demo visitor. Shown wherever
 *  the demo is read-only (Assets, Settings) so a disabled button is never
 *  unexplained. */
export function DemoNotice({ message }: { message?: string }) {
  return (
    <div className="animate-fade-in-up flex items-start gap-3 rounded-lg border border-border bg-surface-variant/50 p-4">
      <Lock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">
        {message ??
          "You're exploring a private demo. Brand settings and assets are read-only so every visitor sees the same sample brand. Generating posts, cards, and documents still works, and your work is removed after 24 hours."}
      </p>
    </div>
  );
}
