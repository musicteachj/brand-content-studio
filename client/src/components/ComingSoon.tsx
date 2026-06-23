import { Construction } from "lucide-react";

/** Placeholder for routes built in later phases (see docs/PLAN.md). */
export function ComingSoon({ title, phase }: { title: string; phase: string }) {
  return (
    <div className="flex min-h-[60vh] animate-fade-in-up flex-col items-center justify-center text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-surface text-muted-foreground shadow-light">
        <Construction className="h-6 w-6" aria-hidden />
      </span>
      <h1 className="mt-5 text-xl font-semibold text-foreground">{title}</h1>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        This view is part of the build roadmap and lands in{" "}
        <span className="font-mono text-foreground">{phase}</span>.
      </p>
    </div>
  );
}
