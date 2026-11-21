import { Link } from "react-router-dom";
import { Brand } from "@/components/Brand";

const PROCESSORS = [
  ["Anthropic", "writes the content"],
  ["OpenAI", "embeds briefs to find matching brand material"],
  ["Cloudflare", "the bot check"],
  ["Unsplash", "image search"],
  ["jsDelivr", "serves the card fonts to your browser"],
  ["AWS", "hosting"],
  ["MongoDB Atlas", "the database"],
] as const;

/** Public at `/privacy`: what the demo keeps, who processes it, and the terms. */
export function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="mx-auto flex w-full max-w-6xl items-center px-6 py-6 sm:px-10">
        <Link
          to="/"
          aria-label="Folio home"
          className="rounded-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Brand />
        </Link>
      </header>

      <main className="mx-auto w-full max-w-3xl px-6 pb-20 pt-8 sm:px-10 lg:pt-12">
        <p className="eyebrow text-[11px]">Folio</p>
        <h1 className="mt-4 text-[clamp(2rem,4vw,3rem)] font-semibold leading-[1.1] tracking-display text-foreground">
          Privacy and terms
        </h1>
        <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
          Folio is a portfolio project by James Littlefield. The public demo has no accounts: each
          visit starts a private demo session that only you can see.
        </p>

        <section aria-labelledby="retention" className="mt-12 border-t border-border pt-8">
          <h2 id="retention" className="text-lg font-semibold tracking-heading text-foreground">
            Retention
          </h2>
          <p className="mt-3 leading-relaxed text-foreground">
            Retention: removed from the app after 24 hours; backups up to 7 days; server logs
            (including IP addresses) 14 days.
          </p>
        </section>

        <section aria-labelledby="processors" className="mt-10 border-t border-border pt-8">
          <h2 id="processors" className="text-lg font-semibold tracking-heading text-foreground">
            Who processes demo data
          </h2>
          <p className="mt-3 leading-relaxed text-foreground">
            Services that process demo data:{" "}
            {PROCESSORS.map(([name, role], i) => (
              <span key={name}>
                {name} ({role})
                {i < PROCESSORS.length - 2 ? ", " : i === PROCESSORS.length - 2 ? ", and " : "."}
              </span>
            ))}
          </p>
          <p className="mt-4 leading-relaxed text-foreground">
            Please don&apos;t enter personal or confidential information.
          </p>
        </section>

        <section aria-labelledby="terms" className="mt-10 border-t border-border pt-8">
          <h2 id="terms" className="text-lg font-semibold tracking-heading text-foreground">
            Terms
          </h2>
          <p className="mt-3 leading-relaxed text-foreground">
            Terms: the demo is provided as is, for evaluation only. Content is written by AI and may
            be inaccurate. Live generation has a budget and may pause; the ready-made examples are
            always available.
          </p>
        </section>

        <p className="mt-12 text-sm text-muted-foreground">
          <a
            href="https://jameslittlefield.net"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-foreground underline underline-offset-4 hover:text-accent"
          >
            jameslittlefield.net
          </a>
        </p>
      </main>
    </div>
  );
}
