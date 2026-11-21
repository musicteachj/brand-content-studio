import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

/** A generation error: the message, plus a link to the ready-made examples, so a failed
 *  generation is never a dead end whatever the cause. */
export function GenerationError({
  message,
  className,
}: {
  message: string | null;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("text-sm text-destructive", className)}>
      <p>{message ?? "Generation failed."}</p>
      <Link
        to="/examples"
        className="mt-2 inline-block font-medium text-foreground underline underline-offset-2 hover:text-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
      >
        Browse the ready-made examples
      </Link>
    </div>
  );
}
