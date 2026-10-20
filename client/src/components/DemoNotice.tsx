import { Lock } from "lucide-react";

/** Explains why controls are disabled for the seeded demo user. Shown wherever
 *  the demo is read-only (Assets, Settings) so a disabled button is never
 *  unexplained. */
export function DemoNotice({ message }: { message?: string }) {
  return (
    <div className="animate-fade-in-up flex items-start gap-3 rounded-lg border border-border bg-surface-variant/50 p-4">
      <Lock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">
        {message ??
          "You're exploring as a demo, so this area is read-only to keep the seeded Verdure workspace intact. Generating posts, cards, and documents still works."}
      </p>
    </div>
  );
}
