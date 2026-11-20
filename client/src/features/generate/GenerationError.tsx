import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

/** Refusals about budget, rate limits, or provider trouble: each one points at the free path. */
const POINTS_AT_EXAMPLES = new Set([
  "live_ai_paused",
  "visitor_allowance",
  "live_ai_unavailable",
  "rate_limited",
]);

/** A generation error: the message, plus a link to the ready-made examples when the
 *  refusal is about budget, rate limits, or provider trouble (never a dead end). */
export function GenerationError({
  message,
  code,
  className,
}: {
  message: string | null;
  code?: string | null;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("text-sm text-destructive", className)}>
      <p>{message ?? "Generation failed."}</p>
      {code && POINTS_AT_EXAMPLES.has(code) && (
        <Link
          to="/examples"
          className="mt-2 inline-block font-medium text-foreground underline underline-offset-2 hover:text-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        >
          Browse the ready-made examples
        </Link>
      )}
    </div>
  );
}
