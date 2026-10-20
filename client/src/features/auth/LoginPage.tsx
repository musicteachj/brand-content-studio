import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight } from "lucide-react";
import { Brand } from "@/components/Brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthActions } from "./useAuthActions";

export function LoginPage() {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <BrandPanel />
      <AuthPanel />
    </div>
  );
}

/* Left: the product story. The tilted "card" hints at the hero output without
   shouting: a quiet preview on the preview-bg surround (DESIGN.md §0). */
function BrandPanel() {
  return (
    <aside className="relative hidden flex-col justify-between overflow-hidden border-r border-border bg-preview-bg px-12 py-10 lg:flex">
      <Brand className="animate-fade-in-up" />

      <div className="max-w-md animate-fade-in-up" style={{ animationDelay: "60ms" }}>
        <p className="eyebrow text-[11px]">Retrieval-augmented · on-brand</p>
        <h1 className="mt-5 text-[2.5rem] font-semibold leading-[1.08] tracking-display text-foreground">
          Your brand’s voice. Retrieved, not invented.
        </h1>
        <p className="mt-5 text-[15px] leading-relaxed text-muted-foreground">
          Folio ingests a brand’s guidelines and past posts, then retrieves the relevant pieces at
          write-time so every LinkedIn post and card sounds unmistakably on-brand.
        </p>
      </div>

      <div
        className="animate-fade-in-up rounded-xl border border-border bg-surface p-5 shadow-preview"
        style={{ animationDelay: "120ms" }}
      >
        <p className="eyebrow">Verdure Materials · retrieved 6 sources</p>
        <p className="mt-3 text-[15px] leading-relaxed text-foreground">
          Hempcrete sequesters ~110&nbsp;kg of CO₂ per cubic meter. That’s not an offset we bought.
          It’s carbon locked into the wall for the life of the building.
        </p>
        <div className="mt-4 flex items-center gap-2 eyebrow">
          <span className="h-1.5 w-1.5 rounded-full bg-success" aria-hidden />
          On-brand · ready to export
        </div>
      </div>
    </aside>
  );
}

function AuthPanel() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // useAuthActions drives the demo + password flows.
  const { loginDemo, loginPassword, pending, error } = useAuthActions();

  // One sign-in at a time, so two flows can't race to set the session.
  const busy = pending !== null;

  async function onDemo() {
    if (busy) return;
    try {
      await loginDemo();
      navigate("/", { replace: true });
    } catch {
      /* error surfaced below */
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    try {
      await loginPassword(email, password);
      navigate("/", { replace: true });
    } catch {
      /* error surfaced below */
    }
  }

  return (
    <main className="flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm animate-fade-in-up">
        <div className="lg:hidden">
          <Brand />
        </div>

        <h2 className="mt-8 text-2xl font-semibold tracking-heading text-foreground lg:mt-0">
          Sign in
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Explore the studio with a ready-made demo workspace, or sign in.
        </p>

        <Button
          size="lg"
          className="mt-7 w-full"
          loading={pending === "demo"}
          disabled={busy}
          onClick={onDemo}
        >
          Explore as demo
          {pending !== "demo" && <ArrowRight className="h-4 w-4" aria-hidden />}
        </Button>

        <div className="my-6 flex items-center gap-3">
          <span className="h-px flex-1 bg-border" />
          <span className="eyebrow">or sign in</span>
          <span className="h-px flex-1 bg-border" />
        </div>

        {error && (
          <div
            role="alert"
            className="mb-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-sm text-destructive"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium text-foreground">
              Email
            </label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@studio.com"
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium text-foreground">
              Password
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <Button
            type="submit"
            variant="secondary"
            className="mt-1 w-full"
            loading={pending === "password"}
            disabled={busy}
          >
            Sign in
          </Button>
        </form>
      </div>
    </main>
  );
}
