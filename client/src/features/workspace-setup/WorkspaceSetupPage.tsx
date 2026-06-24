import { useState } from "react";
import { AxiosError } from "axios";
import { ArrowRight, Check, FolderPlus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCreateWorkspace } from "@/api/workspaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace";

const STEPS = ["Name", "Add assets"] as const;

export function WorkspaceSetupPage() {
  const navigate = useNavigate();
  const create = useCreateWorkspace();
  const setActive = useWorkspaceStore((s) => s.setActive);
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function createWorkspace() {
    setError(null);
    try {
      const ws = await create.mutateAsync({ name: name.trim() });
      setActive(ws.id);
      setStep(1);
    } catch (err) {
      const detail =
        err instanceof AxiosError && typeof err.response?.data?.detail === "string"
          ? err.response.data.detail
          : "Couldn't create workspace.";
      setError(detail);
    }
  }

  return (
    <div className="mx-auto max-w-lg animate-fade-in-up">
      <header className="text-center">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-surface text-muted-foreground shadow-light">
          <FolderPlus className="h-6 w-6" aria-hidden />
        </span>
        <h1 className="mt-5 text-2xl font-semibold tracking-[-0.01em] text-foreground">
          Create a workspace
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          A workspace holds one brand's corpus and generations.
        </p>
      </header>

      <ol className="mt-8 flex items-center justify-center gap-3">
        {STEPS.map((label, i) => (
          <li key={label} className="flex items-center gap-3">
            <span
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium",
                i < step
                  ? "border-accent bg-accent text-accent-foreground"
                  : i === step
                    ? "border-accent text-accent"
                    : "border-border text-muted-foreground",
              )}
            >
              {i < step ? <Check className="h-3.5 w-3.5" aria-hidden /> : i + 1}
            </span>
            <span
              className={cn(
                "text-sm",
                i === step ? "font-medium text-foreground" : "text-muted-foreground",
              )}
            >
              {label}
            </span>
            {i < STEPS.length - 1 && <span className="h-px w-8 bg-border" aria-hidden />}
          </li>
        ))}
      </ol>

      <div className="mt-8 rounded-lg border border-border bg-surface p-6 shadow-light">
        {step === 0 ? (
          <div>
            <Label htmlFor="ws-name">Workspace name</Label>
            <Input
              id="ws-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Verdure Materials"
              onKeyDown={(e) => e.key === "Enter" && name.trim() && createWorkspace()}
            />
            {error && (
              <p role="alert" className="mt-2 text-sm text-destructive">
                {error}
              </p>
            )}
            <Button
              className="mt-5 w-full"
              onClick={createWorkspace}
              disabled={name.trim().length === 0 || create.isPending}
              loading={create.isPending}
            >
              Continue
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Button>
          </div>
        ) : (
          <div className="text-center">
            <p className="text-sm font-medium text-foreground">Workspace created</p>
            <p className="mx-auto mt-1 max-w-xs text-sm text-muted-foreground">
              Now upload brand documents to build the retrievable corpus, then start generating.
            </p>
            <div className="mt-5 flex flex-col gap-2">
              <Button onClick={() => navigate("/assets")}>
                Add brand assets
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Button>
              <Button variant="ghost" onClick={() => navigate("/")}>
                Skip for now
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
