// The branded document, rendered as "paper" in the workspace's own colors and
// fonts — the same structured model the server pours into the .docx / PDF, so
// the preview reads like the file (preview == file). Brand colors arrive as data
// (inline styles, like the card preview); app chrome never leaks in (DESIGN §7).
import { useEffect } from "react";
import { bodyFamily, headingFamily, injectBrandFontFaces } from "@/styles/brandFonts";
import { cn } from "@/lib/utils";
import type { BrandProfile, DocumentModel } from "@/types";
import { documentColors } from "./documentColors";

interface Props {
  document: DocumentModel;
  brand: BrandProfile;
  /** Header-only render for grid thumbnails (eyebrow + title + lede). */
  compact?: boolean;
  className?: string;
}

export function DocumentPage({ document: doc, brand, compact = false, className }: Props) {
  const colors = documentColors(brand);
  const heading = headingFamily(brand.fonts);
  const body = bodyFamily(brand.fonts);

  // Load the workspace @font-face so the paper renders in brand type, not the app's.
  useEffect(() => {
    injectBrandFontFaces(brand.fonts, brand.uploaded_fonts ?? []);
  }, [brand.fonts, brand.uploaded_fonts]);

  const headingStack = `"${heading}", Georgia, "Times New Roman", serif`;
  const bodyStack = `"${body}", Georgia, "Times New Roman", serif`;

  return (
    <div
      className={cn("bg-white", compact ? "px-5 py-5" : "px-8 py-9 sm:px-12 sm:py-12", className)}
      style={{ fontFamily: bodyStack, color: colors.ink }}
    >
      {doc.eyebrow && (
        <p
          className={cn(
            "font-medium uppercase",
            compact ? "text-[10px] tracking-[0.16em]" : "text-[11px] tracking-[0.18em]",
          )}
          style={{ color: colors.accent }}
        >
          {doc.eyebrow}
        </p>
      )}

      {doc.title && (
        <h2
          className={cn(
            "mt-1.5 font-semibold leading-[1.12]",
            compact ? "text-lg" : "text-[26px] sm:text-[32px]",
          )}
          style={{ fontFamily: headingStack, color: colors.primary }}
        >
          {doc.title}
        </h2>
      )}

      {doc.lede && (
        <p
          className={cn(
            "mt-3 leading-relaxed",
            compact ? "line-clamp-2 text-xs" : "text-[15px] sm:text-base",
          )}
          style={{ color: colors.ink }}
        >
          {doc.lede}
        </p>
      )}

      {!compact && (
        <>
          {doc.sections.map((section, i) => (
            <section key={i} className="mt-6">
              {section.heading && (
                <h3
                  className="text-lg font-semibold leading-snug"
                  style={{ fontFamily: headingStack, color: colors.primary }}
                >
                  {section.heading}
                </h3>
              )}
              {section.body && (
                <p className="mt-1.5 text-[15px] leading-relaxed" style={{ color: colors.ink }}>
                  {section.body}
                </p>
              )}
              {section.bullets.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {section.bullets.map((b, j) => (
                    <li key={j} className="flex gap-2 text-[15px] leading-relaxed">
                      <span aria-hidden style={{ color: colors.accent }}>
                        •
                      </span>
                      <span style={{ color: colors.ink }}>{b}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}

          {doc.footer && (
            <p
              className="mt-8 border-t pt-4 text-xs"
              style={{ color: colors.muted, borderColor: "rgba(0,0,0,0.08)" }}
            >
              {doc.footer}
            </p>
          )}
        </>
      )}
    </div>
  );
}
