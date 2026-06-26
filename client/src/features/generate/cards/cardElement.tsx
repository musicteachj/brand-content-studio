/* eslint-disable react-refresh/only-export-components -- this module intentionally
   exports the card-element builder + colour/size helpers alongside the archetypes;
   it is consumed as a library, not HMR-mounted as a route component. */
// The three card archetypes (PhotoLed · Statement · Quote), authored in Satori's
// flexbox/CSS subset using ONLY workspace fonts + colors (never Folio chrome —
// DESIGN §7). `buildCardElement` returns ONE React element that is rendered three
// ways: the live DOM typing preview, the locked Satori preview, and the PNG
// export. Because all three consume the same element + the same fonts, the
// preview equals the export by construction (ARCHITECTURE §5).
import type { CSSProperties, ReactElement } from "react";
import { bodyFamily, headingFamily } from "@/styles/brandFonts";
import type { BrandProfile, CardFields, CardTemplate, ImageAttribution } from "@/types";

export const CARD_W = 1080;
export const CARD_H = 1350;

/** Only the photo-led archetype uses a picked image; statement & quote are
 *  purely typographic on a brand-color field. */
export function templateUsesImage(template: CardTemplate): boolean {
  return template === "photo-led";
}

interface CardColors {
  ink: string; // primary / dark
  paper: string; // neutral / light
  accent: string;
}

function roleHex(brand: BrandProfile, role: string, fallback: string): string {
  return brand.colors.find((c) => c.role === role)?.hex ?? fallback;
}

export function cardColors(brand: BrandProfile): CardColors {
  const ink = roleHex(brand, "primary", "#1C3A2E");
  const paper = roleHex(brand, "neutral", "#F4F1E9");
  const accent =
    brand.accent_hex && brand.accent_hex !== ink
      ? brand.accent_hex
      : roleHex(brand, "accent", roleHex(brand, "secondary", "#C98A3D"));
  return { ink, paper, accent };
}

export interface CardElementProps {
  template: CardTemplate;
  fields: CardFields;
  brand: BrandProfile;
  imageSrc: string | null; // data URL (export + DOM) for photo-led
  attribution: ImageAttribution | null;
}

const PAD = 88;

// The brand web fonts are loaded as the "latin" subset, which has no arrows,
// emoji, or symbol glyphs — Satori renders those as a missing-glyph box (tofu).
// The model occasionally puts a "→" in a CTA, so strip those ranges at render time
// (General Punctuation — em/en dashes, curly quotes, ellipsis — is kept).
const UNRENDERABLE = /[\u{2190}-\u{21FF}\u{2300}-\u{27BF}\u{2B00}-\u{2BFF}\u{1F000}-\u{1FAFF}]/gu;

export function cleanGlyphs(text: string): string {
  return text
    .replace(UNRENDERABLE, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function cleanFields(fields: CardFields): CardFields {
  return {
    eyebrow: cleanGlyphs(fields.eyebrow),
    headline: cleanGlyphs(fields.headline),
    body: cleanGlyphs(fields.body),
    cta: cleanGlyphs(fields.cta),
    hashtag: cleanGlyphs(fields.hashtag),
  };
}

function eyebrowStyle(color: string, body: string): CSSProperties {
  return {
    fontFamily: body,
    fontSize: 25,
    fontWeight: 600,
    letterSpacing: 5,
    textTransform: "uppercase",
    color,
  };
}

function attributionEl(attribution: ImageAttribution, color: string, body: string): ReactElement {
  // Baked onto the card — Unsplash license requires visible credit (gotcha #4).
  return (
    <div
      style={{
        display: "flex",
        position: "absolute",
        right: PAD,
        bottom: 36,
        fontFamily: body,
        fontSize: 19,
        color,
        opacity: 0.92,
      }}
    >
      Photo by {attribution.author} on Unsplash
    </div>
  );
}

function PhotoLed(props: CardElementProps): ReactElement {
  const { fields, brand, imageSrc, attribution } = props;
  const c = cardColors(brand);
  const heading = headingFamily(brand.fonts);
  const body = bodyFamily(brand.fonts);
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        width: CARD_W,
        height: CARD_H,
        position: "relative",
        backgroundColor: c.ink,
        fontFamily: body,
        overflow: "hidden",
      }}
    >
      {imageSrc ? (
        <img
          src={imageSrc}
          width={CARD_W}
          height={CARD_H}
          style={{ position: "absolute", top: 0, left: 0, objectFit: "cover" }}
        />
      ) : null}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: CARD_W,
          height: CARD_H,
          backgroundImage: `linear-gradient(180deg, rgba(0,0,0,0) 38%, ${hexToRgba(c.ink, 0.55)} 70%, ${hexToRgba(c.ink, 0.92)} 100%)`,
        }}
      />
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          position: "absolute",
          left: PAD,
          right: PAD,
          bottom: 96,
        }}
      >
        {fields.eyebrow ? (
          <div style={{ ...eyebrowStyle(c.accent, body), marginBottom: 22 }}>{fields.eyebrow}</div>
        ) : null}
        <div
          style={{
            fontFamily: heading,
            fontSize: 80,
            fontWeight: 700,
            lineHeight: 1.04,
            color: c.paper,
          }}
        >
          {fields.headline}
        </div>
        {fields.body ? (
          <div
            style={{
              fontFamily: body,
              fontSize: 30,
              lineHeight: 1.4,
              color: c.paper,
              opacity: 0.9,
              marginTop: 26,
            }}
          >
            {fields.body}
          </div>
        ) : null}
        <Footer
          cta={fields.cta}
          hashtag={fields.hashtag}
          color={c.paper}
          accent={c.accent}
          body={body}
        />
      </div>
      {attribution ? attributionEl(attribution, c.paper, body) : null}
    </div>
  );
}

function Statement(props: CardElementProps): ReactElement {
  const { fields, brand } = props;
  const c = cardColors(brand);
  const heading = headingFamily(brand.fonts);
  const body = bodyFamily(brand.fonts);
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        width: CARD_W,
        height: CARD_H,
        position: "relative",
        backgroundColor: c.ink,
        fontFamily: body,
        padding: PAD,
      }}
    >
      <div style={{ display: "flex" }}>
        {fields.eyebrow ? <div style={eyebrowStyle(c.accent, body)}>{fields.eyebrow}</div> : null}
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        <div
          style={{
            display: "flex",
            width: 96,
            height: 6,
            backgroundColor: c.accent,
            marginBottom: 40,
          }}
        />
        <div
          style={{
            fontFamily: heading,
            fontSize: 94,
            fontWeight: 700,
            lineHeight: 1.02,
            color: c.paper,
          }}
        >
          {fields.headline}
        </div>
        {fields.body ? (
          <div
            style={{
              fontFamily: body,
              fontSize: 30,
              lineHeight: 1.45,
              color: c.paper,
              opacity: 0.82,
              marginTop: 34,
            }}
          >
            {fields.body}
          </div>
        ) : null}
      </div>
      <Footer
        cta={fields.cta}
        hashtag={fields.hashtag}
        color={c.paper}
        accent={c.accent}
        body={body}
      />
    </div>
  );
}

function Quote(props: CardElementProps): ReactElement {
  const { fields, brand } = props;
  const c = cardColors(brand);
  const heading = headingFamily(brand.fonts);
  const body = bodyFamily(brand.fonts);
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        width: CARD_W,
        height: CARD_H,
        position: "relative",
        backgroundColor: c.paper,
        fontFamily: body,
        padding: PAD,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column" }}>
        {fields.eyebrow ? (
          <div style={{ ...eyebrowStyle(c.accent, body), marginBottom: 8 }}>{fields.eyebrow}</div>
        ) : null}
        <div
          style={{
            display: "flex",
            fontFamily: heading,
            fontSize: 200,
            lineHeight: 0.8,
            color: c.accent,
          }}
        >
          &ldquo;
        </div>
      </div>
      <div
        style={{
          fontFamily: heading,
          fontSize: 70,
          fontWeight: 400,
          lineHeight: 1.16,
          color: c.ink,
          marginTop: -40,
        }}
      >
        {fields.headline}
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {fields.body ? (
          <div
            style={{
              fontFamily: body,
              fontSize: 27,
              color: c.ink,
              opacity: 0.75,
              marginBottom: 18,
            }}
          >
            {fields.body}
          </div>
        ) : null}
        <Footer
          cta={fields.cta}
          hashtag={fields.hashtag}
          color={c.ink}
          accent={c.accent}
          body={body}
        />
      </div>
    </div>
  );
}

function Footer({
  cta,
  hashtag,
  color,
  accent,
  body,
}: {
  cta: string;
  hashtag: string;
  color: string;
  accent: string;
  body: string;
}): ReactElement | null {
  if (!cta && !hashtag) return null;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginTop: 38,
      }}
    >
      <div style={{ fontFamily: body, fontSize: 28, fontWeight: 600, color }}>{cta}</div>
      {hashtag ? (
        <div style={{ fontFamily: body, fontSize: 26, color: accent }}>{hashtag}</div>
      ) : null}
    </div>
  );
}

export function buildCardElement(props: CardElementProps): ReactElement {
  // Sanitize once here so every render path (preview, export, history thumbnail)
  // is glyph-safe.
  const safe: CardElementProps = { ...props, fields: cleanFields(props.fields) };
  switch (safe.template) {
    case "statement":
      return <Statement {...safe} />;
    case "quote":
      return <Quote {...safe} />;
    case "photo-led":
    default:
      return <PhotoLed {...safe} />;
  }
}

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const full =
    h.length === 3
      ? h
          .split("")
          .map((x) => x + x)
          .join("")
      : h;
  const r = parseInt(full.slice(0, 2), 16) || 0;
  const g = parseInt(full.slice(2, 4), 16) || 0;
  const b = parseInt(full.slice(4, 6), 16) || 0;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
