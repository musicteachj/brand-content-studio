import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { IngestionStatus } from "@/types";

// Color is never the sole signal — each status pairs an icon + label (DESIGN §6).
const CONFIG: Record<
  IngestionStatus,
  { label: string; icon: typeof CheckCircle2; className: string; spin?: boolean }
> = {
  processing: {
    label: "Processing",
    icon: Loader2,
    className: "text-warning",
    spin: true,
  },
  ready: { label: "Ready", icon: CheckCircle2, className: "text-success" },
  error: { label: "Error", icon: AlertTriangle, className: "text-destructive" },
};

export function StatusPill({ status }: { status: IngestionStatus }) {
  const { label, icon: Icon, className, spin } = CONFIG[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em]",
        className,
      )}
    >
      <Icon className={cn("h-3 w-3", spin && "animate-spin")} aria-hidden />
      {label}
    </span>
  );
}
