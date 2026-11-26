import { cn } from "@/lib/utils";
import type { ImageAttribution } from "@/types";

/** Unsplash's home page, tagged with the same UTM referral params the server puts on
 *  the author and photo links (`_UTM` in server/app/services/unsplash_service.py). */
const UNSPLASH_HOME_URL = "https://unsplash.com/?utm_source=Folio&utm_medium=referral";

const LINK = "underline decoration-border underline-offset-2 hover:text-foreground";

/** The server builds `author_url` from Unsplash's own profile link, but a saved card's
 *  attribution comes back through PATCH as a plain string, so only an https link on
 *  unsplash.com is rendered as a link. Anything else shows the name as plain text. */
function isUnsplashLink(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && parsed.hostname === "unsplash.com";
  } catch {
    return false;
  }
}

function CreditLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={LINK}
      // The picker's credit sits beside a select button; following it must not pick.
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </a>
  );
}

/** "Photo by X on Unsplash", with the photographer and Unsplash each linked (new tab),
 *  per the Unsplash API attribution guidelines. Always visible, never a tooltip. */
export function UnsplashCredit({
  attribution,
  className,
}: {
  attribution: ImageAttribution;
  className?: string;
}) {
  return (
    <p className={cn("text-[11px] leading-tight text-muted-foreground", className)}>
      Photo by{" "}
      {isUnsplashLink(attribution.author_url) ? (
        <CreditLink href={attribution.author_url}>{attribution.author}</CreditLink>
      ) : (
        attribution.author
      )}{" "}
      on <CreditLink href={UNSPLASH_HOME_URL}>Unsplash</CreditLink>
    </p>
  );
}
