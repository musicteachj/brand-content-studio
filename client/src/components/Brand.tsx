import { cn } from "@/lib/utils";

/** Folio wordmark. The ink "F" mark stays disciplined — accent is for actions only. */
export function Brand({
  collapsed = false,
  className,
}: {
  collapsed?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-foreground font-display text-base font-semibold text-background">
        F
      </span>
      {!collapsed && (
        <span className="flex flex-col leading-none">
          <span className="font-display text-[15px] font-semibold tracking-heading text-foreground">
            Folio
          </span>
          <span className="mt-[3px] eyebrow">Studio</span>
        </span>
      )}
    </div>
  );
}
