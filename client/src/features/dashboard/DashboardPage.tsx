import { ArrowRight, FileText, PenLine, Sparkle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useGenerationCount } from "@/api/generations";
import { Button } from "@/components/ui/button";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { useAuthStore } from "@/stores/auth";

export function DashboardPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const firstName = (user?.full_name ?? "there").split(" ")[0];
  const { workspace, workspaceId, isError, hasNone } = useActiveWorkspace();
  const { data: generationCount } = useGenerationCount(workspaceId);

  return (
    <div className="flex flex-col gap-8">
      <header className="animate-fade-in-up">
        <p className="eyebrow text-[11px]">Dashboard</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-heading text-foreground">
          Welcome back, {firstName}.
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          Ingest brand assets, then generate on-brand LinkedIn posts, cards, and documents from the
          retrieved corpus.
        </p>
      </header>

      {isError && (
        <div className="rounded-lg border border-border bg-surface p-4 text-sm text-destructive">
          Couldn't load this workspace. Is the server running?
        </div>
      )}

      {hasNone ? (
        <div
          className="animate-fade-in-up rounded-lg border border-border bg-surface p-8 text-center shadow-light"
          style={{ animationDelay: "60ms" }}
        >
          <h2 className="text-base font-semibold text-foreground">Create your first workspace</h2>
          <p className="mx-auto mt-1.5 max-w-sm text-sm text-muted-foreground">
            A workspace holds one brand's corpus and generations. Create one to start ingesting
            assets and generating on-brand content.
          </p>
          <Button className="mt-5" onClick={() => navigate("/setup")}>
            Create workspace
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      ) : (
        <>
          <div
            className="grid animate-fade-in-up gap-4 sm:grid-cols-3"
            style={{ animationDelay: "60ms" }}
          >
            <StatCard
              label="Brand assets"
              value={String(workspace?.asset_count ?? 0)}
              hint="Ingested documents"
            />
            <StatCard
              label="Ready chunks"
              value={String(workspace?.ready_chunk_count ?? 0)}
              hint="Retrievable corpus"
            />
            <StatCard
              label="Generations"
              value={String(generationCount ?? 0)}
              hint="Posts, cards, and documents"
            />
          </div>

          <div
            className="grid animate-fade-in-up gap-4 sm:grid-cols-2"
            style={{ animationDelay: "120ms" }}
          >
            <ActionCard
              icon={FileText}
              title="Ingest brand assets"
              body="Upload voice guides and past posts to build the retrievable corpus."
              cta="Open Asset Manager"
              onClick={() => navigate("/assets")}
            />
            <ActionCard
              icon={PenLine}
              title="Generate content"
              body="Write an on-brand LinkedIn post or designed card from a brief."
              cta="Open Generate"
              primary
              onClick={() => navigate("/generate")}
            />
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-5 shadow-light">
      <p className="eyebrow">{label}</p>
      <p className="mt-3 text-3xl font-semibold tracking-display text-foreground">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

function ActionCard({
  icon: Icon,
  title,
  body,
  cta,
  onClick,
  primary = false,
}: {
  icon: typeof Sparkle;
  title: string;
  body: string;
  cta: string;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <div className="flex flex-col rounded-lg border border-border bg-surface p-6 shadow-light transition-shadow hover:shadow-medium">
      <span className="flex h-10 w-10 items-center justify-center rounded-md bg-surface-variant text-foreground">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <h2 className="mt-4 text-base font-semibold text-foreground">{title}</h2>
      <p className="mt-1.5 flex-1 text-sm text-muted-foreground">{body}</p>
      <Button
        variant={primary ? "primary" : "secondary"}
        size="sm"
        className="mt-5 self-start"
        onClick={onClick}
      >
        {cta}
        <ArrowRight className="h-4 w-4" aria-hidden />
      </Button>
    </div>
  );
}
