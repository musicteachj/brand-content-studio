import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowRight, Info, PauseCircle } from "lucide-react";
import { DEMO_ENDED_COPY, LIVE_AI_PAUSED_COPY, useAppStatus } from "@/api/status";
import { Brand } from "@/components/Brand";
import { Button } from "@/components/ui/button";
import { PasswordSignInForm } from "@/features/auth/PasswordSignInForm";
import { useAuthActions } from "@/features/auth/useAuthActions";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

/** The four screenshots under the pitch (copies of docs/screenshots in public/). */
const SCREENSHOTS = [
  {
    src: "/screenshots/linkedin-post.jpg",
    title: "LinkedIn post",
    caption: "A caption and its matching card, from one brief.",
    alt: "Folio's Generate page in LinkedIn post mode: a brief about a housing co-op switching to hempcrete walls, a photo-led Verdure card headlined “41 kg less CO2 per square meter. Per wall.”, and the matching post caption beside it.",
  },
  {
    src: "/screenshots/image-card.jpg",
    title: "Image card",
    caption: "Brand layouts, colors, and fonts, exported as a PNG.",
    alt: "Folio's Generate page in Image card mode: the Statement layout is selected and the preview shows a dark green Verdure card headlined “The carbon you don't specify costs nothing.”, with Edit text and Export PNG buttons below it.",
  },
  {
    src: "/screenshots/document.jpg",
    title: "Document",
    caption: "A branded one-pager or deck, as .docx, PDF, or .pptx.",
    alt: "Folio's Generate page in Document mode: a one-pager titled “Hempcrete Wall Panels for Mid-Rise Residential”, set in Verdure's serif fonts with green section headings.",
  },
  {
    src: "/screenshots/retrieved-context.jpg",
    title: "Retrieved context",
    caption: "Every generation shows the brand material it drew on.",
    alt: "Folio's Retrieved context panel under a generated post: pinned excerpts from the brand's content-pillars.md, each tagged with its kind, that the model was given before writing.",
  },
] as const;

type Flow = "demo" | "password";

/** The signed-out front door at `/`: the live demo (a bot check, then the studio) side by
 *  side with the ready-made examples (no demo start, no bot check). */
export function StartPage() {
  const status = useAppStatus();
  const demoEnded = useAuthStore((s) => s.endedReason === "ended");
  // Unknown until the status loads: the button reads "Try it live" and the form stays hidden,
  // so production never flashes a sign-in it has closed.
  const paused = status.data?.live_ai_available === false;
  const passwordLogin = status.data?.password_login === true;

  const { loginDemo, loginPassword, pending, error } = useAuthActions();
  // Which flow the visitor last tried, so its error shows next to it.
  const [flow, setFlow] = useState<Flow>("demo");
  // The bot check's widget renders here, under the buttons, and stays invisible unless
  // Cloudflare needs a click.
  const turnstileSlot = useRef<HTMLDivElement>(null);
  // One sign-in at a time, so two flows can't race to set the session.
  const busy = pending !== null;

  // On success the session is stored and `/` becomes the dashboard on its own.
  async function onStart() {
    if (busy) return;
    setFlow("demo");
    try {
      await loginDemo(turnstileSlot.current);
    } catch {
      /* error surfaced below */
    }
  }

  async function onPassword(email: string, password: string) {
    if (busy) return;
    setFlow("password");
    try {
      await loginPassword(email, password);
    } catch {
      /* error surfaced below */
    }
  }

  const live = (
    <Button
      key="live"
      size="lg"
      variant={paused ? "secondary" : "primary"}
      loading={pending === "demo"}
      disabled={busy}
      onClick={() => void onStart()}
    >
      {paused ? "Explore the studio" : "Try it live"}
      {pending !== "demo" && <ArrowRight className="h-4 w-4" aria-hidden />}
    </Button>
  );
  // While live generation is off the examples are the better path, so they lead.
  const examples = (
    <Button key="examples" asChild size="lg" variant={paused ? "primary" : "secondary"}>
      <Link to="/examples">See ready-made examples</Link>
    </Button>
  );

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="mx-auto flex w-full max-w-6xl items-center px-6 py-6 sm:px-10">
        <Brand />
      </header>

      <main>
        <section className="mx-auto w-full max-w-6xl px-6 pb-16 pt-8 sm:px-10 lg:pb-24 lg:pt-16">
          <div className="max-w-4xl animate-fade-in-up">
            <p className="eyebrow text-[11px]">Brand content studio · Retrieval-augmented</p>
            <h1 className="mt-5 text-[clamp(2.75rem,6vw,4.5rem)] font-semibold leading-[1.04] tracking-display text-foreground">
              Your brand’s voice. Retrieved, not invented.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
              Folio turns a brand’s guidelines and past posts into on-brand LinkedIn posts, image
              cards, and documents.
            </p>

            {demoEnded && (
              <div
                role="status"
                className="mt-8 flex max-w-xl items-start gap-3 rounded-lg border border-border bg-surface-variant/50 p-4"
              >
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <p className="text-sm text-foreground">{DEMO_ENDED_COPY}</p>
              </div>
            )}

            {paused && (
              <div
                role="status"
                className="mt-8 flex max-w-xl items-start gap-3 rounded-lg border border-border bg-surface-variant/50 p-4"
              >
                <PauseCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
                <p className="text-sm text-foreground">{LIVE_AI_PAUSED_COPY}</p>
              </div>
            )}

            <div className={paused ? "mt-6" : "mt-10"}>
              <div className="flex flex-wrap items-center gap-3">
                {paused ? [examples, live] : [live, examples]}
              </div>
              <div ref={turnstileSlot} className="mt-3 empty:hidden" />
              <p className="mt-4 text-sm text-muted-foreground">
                No sign-up. The demo uses Verdure Materials, a sample brand, for 24 hours.
              </p>
              {error && flow === "demo" && <ErrorAlert message={error} className="mt-5 max-w-xl" />}
            </div>
          </div>
        </section>

        <section aria-labelledby="studio-tour" className="border-t border-border bg-preview-bg">
          <div className="mx-auto w-full max-w-6xl px-6 py-14 sm:px-10 lg:py-20">
            <h2 id="studio-tour" className="eyebrow text-[11px]">
              Inside the studio
            </h2>
            <ul className="mt-6 grid gap-x-6 gap-y-10 sm:grid-cols-2">
              {SCREENSHOTS.map((shot) => (
                <li key={shot.src}>
                  <figure>
                    <img
                      src={shot.src}
                      alt={shot.alt}
                      width={1600}
                      height={1000}
                      loading="lazy"
                      decoding="async"
                      className="aspect-[16/10] w-full rounded-lg border border-border bg-surface object-cover shadow-medium"
                    />
                    <figcaption className="mt-4">
                      <span className="block text-sm font-semibold text-foreground">
                        {shot.title}
                      </span>
                      <span className="mt-0.5 block text-sm text-muted-foreground">
                        {shot.caption}
                      </span>
                    </figcaption>
                  </figure>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {passwordLogin && (
          <section aria-labelledby="password-sign-in" className="border-t border-border">
            <div className="mx-auto w-full max-w-6xl px-6 py-14 sm:px-10">
              <div className="max-w-sm">
                <p className="eyebrow">Development only</p>
                <h2
                  id="password-sign-in"
                  className="mt-2 text-lg font-semibold tracking-heading text-foreground"
                >
                  Sign in with a password
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Closed in production, where the demo is the way in.
                </p>
                {error && flow === "password" && <ErrorAlert message={error} className="mt-5" />}
                <PasswordSignInForm
                  className="mt-5"
                  onSubmit={(email, password) => void onPassword(email, password)}
                  loading={pending === "password"}
                  disabled={busy}
                />
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function ErrorAlert({ message, className }: { message: string; className?: string }) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-sm text-destructive",
        className,
      )}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}
