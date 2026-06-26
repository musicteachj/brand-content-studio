// The short-deck rendered as branded 16:9 slide cards — the same structured
// model the server pours into the .pptx (title slide → content slides → closing),
// in the workspace's own colors and fonts (never Folio chrome, DESIGN §7).
// `compact` renders the title slide only, for History thumbnails.
import { useEffect, type ReactNode } from "react";
import { bodyFamily, headingFamily, injectBrandFontFaces } from "@/styles/brandFonts";
import { cn } from "@/lib/utils";
import type { BrandProfile, DocumentModel } from "@/types";
import { documentColors } from "./documentColors";

function DeckSlide({
  children,
  bodyStack,
  ink,
  compact,
}: {
  children: ReactNode;
  bodyStack: string;
  ink: string;
  compact: boolean;
}) {
  return (
    <div
      className="aspect-[16/9] w-full overflow-hidden rounded-md bg-white ring-1 ring-border"
      style={{ fontFamily: bodyStack, color: ink }}
    >
      <div
        className={cn("flex h-full flex-col", compact ? "px-4 py-3" : "px-7 py-6 sm:px-9 sm:py-8")}
      >
        {children}
      </div>
    </div>
  );
}

interface Props {
  document: DocumentModel;
  brand: BrandProfile;
  compact?: boolean;
  className?: string;
}

export function DeckPreview({ document: doc, brand, compact = false, className }: Props) {
  const colors = documentColors(brand);
  const heading = headingFamily(brand.fonts);
  const body = bodyFamily(brand.fonts);

  useEffect(() => {
    injectBrandFontFaces(brand.fonts);
  }, [brand.fonts]);

  const headingStack = `"${heading}", Georgia, "Times New Roman", serif`;
  const bodyStack = `"${body}", Georgia, "Times New Roman", serif`;
  const slideProps = { bodyStack, ink: colors.ink, compact };

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* Title slide */}
      <DeckSlide {...slideProps}>
        <div className="flex h-full flex-col justify-center">
          {doc.eyebrow && (
            <p
              className={cn(
                "font-medium uppercase tracking-[0.16em]",
                compact ? "text-[10px]" : "text-[11px] sm:text-xs",
              )}
              style={{ color: colors.accent }}
            >
              {doc.eyebrow}
            </p>
          )}
          <h2
            className={cn(
              "mt-1 font-semibold leading-[1.1]",
              compact ? "text-base" : "text-2xl sm:text-3xl",
            )}
            style={{ fontFamily: headingStack, color: colors.primary }}
          >
            {doc.title}
          </h2>
          {doc.lede && !compact && (
            <p className="mt-3 text-sm leading-relaxed sm:text-base" style={{ color: colors.ink }}>
              {doc.lede}
            </p>
          )}
        </div>
      </DeckSlide>

      {/* Content slides */}
      {!compact &&
        doc.sections.map((section, i) => (
          <DeckSlide key={i} {...slideProps}>
            {section.heading && (
              <h3
                className="text-lg font-semibold sm:text-xl"
                style={{ fontFamily: headingStack, color: colors.primary }}
              >
                {section.heading}
              </h3>
            )}
            {section.body && (
              <p className="mt-2 text-sm leading-relaxed" style={{ color: colors.ink }}>
                {section.body}
              </p>
            )}
            {section.bullets.length > 0 && (
              <ul className="mt-2 space-y-1.5">
                {section.bullets.map((b, j) => (
                  <li key={j} className="flex gap-2 text-sm leading-relaxed">
                    <span aria-hidden style={{ color: colors.accent }}>
                      •
                    </span>
                    <span style={{ color: colors.ink }}>{b}</span>
                  </li>
                ))}
              </ul>
            )}
          </DeckSlide>
        ))}

      {/* Closing slide */}
      {!compact && doc.footer && (
        <DeckSlide {...slideProps}>
          <div className="flex h-full items-center justify-center text-center">
            <p
              className="text-lg font-semibold sm:text-xl"
              style={{ fontFamily: headingStack, color: colors.primary }}
            >
              {doc.footer}
            </p>
          </div>
        </DeckSlide>
      )}
    </div>
  );
}
