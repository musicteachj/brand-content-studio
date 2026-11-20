import { useRef } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight } from "lucide-react";
import { useAppStatus } from "@/api/status";
import { Brand } from "@/components/Brand";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PasswordSignInForm } from "./PasswordSignInForm";
import { useAuthActions } from "./useAuthActions";

/** The development sign-in page at /login. Visitors start on the start page (`/`); where
 *  password sign-in is closed (production), this page sends them there. */
export function LoginPage() {
  const status = useAppStatus();
  if (status.data && !status.data.password_login) return <Navigate to="/" replace />;
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

  // useAuthActions drives the demo + password flows.
  const { loginDemo, loginPassword, pending, error } = useAuthActions();
  // The bot check's widget renders here, under the demo button, and stays invisible unless
  // Cloudflare needs a click.
  const turnstileSlot = useRef<HTMLDivElement>(null);
  // Password sign-in is closed in production. Hidden until the server says it's open, so
  // production never flashes a form that can't work; shown if the status can't be read.
  const status = useAppStatus();
  const passwordLogin = status.data ? status.data.password_login : status.isError;

  // One sign-in at a time, so two flows can't race to set the session.
  const busy = pending !== null;

  async function onDemo() {
    if (busy) return;
    try {
      await loginDemo(turnstileSlot.current);
      navigate("/", { replace: true });
    } catch {
      /* error surfaced below */
    }
  }

  async function onPassword(email: string, password: string) {
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
          {passwordLogin
            ? "Explore the studio with a ready-made demo workspace, or sign in."
            : "Explore the studio with a ready-made demo workspace."}
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
        <div ref={turnstileSlot} className="mt-3 flex justify-center empty:hidden" />

        {passwordLogin && (
          <div className="my-6 flex items-center gap-3">
            <span className="h-px flex-1 bg-border" />
            <span className="eyebrow">or sign in</span>
            <span className="h-px flex-1 bg-border" />
          </div>
        )}

        {error && (
          <div
            role="alert"
            className={cn(
              "flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-sm text-destructive",
              passwordLogin ? "mb-4" : "mt-6",
            )}
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        )}

        {passwordLogin && (
          <PasswordSignInForm
            onSubmit={(email, password) => void onPassword(email, password)}
            loading={pending === "password"}
            disabled={busy}
          />
        )}
      </div>
    </main>
  );
}
