/* eslint-disable react-refresh/only-export-components -- this module intentionally
   exports the card-element builder + colour/size helpers alongside the archetypes;
   it is consumed as a library, not HMR-mounted as a route component. */
// The three card archetypes (PhotoLed · Statement · Quote), authored in Satori's
// flexbox/CSS subset using ONLY workspace fonts + colors (never Folio chrome —
// DESIGN §7). `buildCardElement` returns ONE React element that is rendered three
// ways: the live DOM typing preview, the locked Satori preview, and the PNG
// export. Because all three consume the same element + the same fonts, the
// preview equals the export by construction (ARCHITECTURE §5).
import { useEffect, useRef, type CSSProperties, type ReactElement } from "react";
import { fitTextSize } from "@/features/generate/cards/fitText";
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

/** Resolve the card's three working colors. A per-card `accentOverride` (Phase
 *  1.5 accent toggle) wins over the workspace `--accent` tint, which wins over
 *  the brand's accent/secondary role. The override is validated against the
 *  palette server-side, so it is always an on-brand color. */
export function cardColors(brand: BrandProfile, accentOverride?: string | null): CardColors {
  const ink = roleHex(brand, "primary", "#1C3A2E");
  const paper = roleHex(brand, "neutral", "#F4F1E9");
  const fallbackAccent =
    brand.accent_hex && brand.accent_hex !== ink
      ? brand.accent_hex
      : roleHex(brand, "accent", roleHex(brand, "secondary", "#C98A3D"));
  const accent = accentOverride && accentOverride !== ink ? accentOverride : fallbackAccent;
  return { ink, paper, accent };
}

/** When present (DOM edit mode only — never Satori/export), the card's text
 *  fields render as in-place contentEditable nodes wired to `onEdit`. */
export interface CardEditHandlers {
  onEdit: (key: keyof CardFields, value: string) => void;
}

export interface CardElementProps {
  template: CardTemplate;
  fields: CardFields;
  brand: BrandProfile;
  imageSrc: string | null; // data URL (export + DOM) for photo-led
  attribution: ImageAttribution | null;
  accentHex?: string | null; // per-card accent override (Phase 1.5)
  edit?: CardEditHandlers; // in-place inline editing (Phase 1.5); DOM-only
}

const PAD = 88;
const INNER_W = CARD_W - PAD * 2;

// Per-archetype headline fit: the design ("max") size and how much vertical room
// the headline may take before it crowds the rest of the card. fitTextSize steps
// down from max so long / swapped-in copy never clips (Phase 1.5).
const HEADLINE_FIT: Record<
  CardTemplate,
  { max: number; min: number; lineHeight: number; boxHeight: number }
> = {
  "photo-led": { max: 80, min: 46, lineHeight: 1.04, boxHeight: 470 },
  statement: { max: 94, min: 50, lineHeight: 1.02, boxHeight: 600 },
  quote: { max: 70, min: 42, lineHeight: 1.16, boxHeight: 540 },
};

function headlineSize(template: CardTemplate, text: string): number {
  const f = HEADLINE_FIT[template];
  return fitTextSize({
    text,
    max: f.max,
    min: f.min,
    lineHeight: f.lineHeight,
    boxWidth: INNER_W,
    boxHeight: f.boxHeight,
  });
}

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

/** A single contentEditable card field. Uncontrolled: seeded once on mount and
 *  never re-written from props, so the caret never jumps while typing; edits flow
 *  out via `onInput`. Remount (via a `key` on the parent) re-seeds when the
 *  generation/template changes. The placeholder + dashed affordance come from the
 *  `.card-edit-field` class (index.css) so empty fields stay clickable. */
function EditableText({
  fieldKey,
  initial,
  style,
  placeholder,
  onEdit,
}: {
  fieldKey: keyof CardFields;
  initial: string;
  style: CSSProperties;
  placeholder: string;
  onEdit: CardEditHandlers["onEdit"];
}): ReactElement {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el && el.textContent !== initial) el.textContent = initial;
    // Seed once; intentionally not reacting to `initial` changes (would reset caret).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      role="textbox"
      aria-label={placeholder}
      data-placeholder={placeholder}
      tabIndex={0}
      spellCheck={false}
      onInput={(e) => onEdit(fieldKey, e.currentTarget.textContent ?? "")}
      className="card-edit-field"
      style={{ ...style, whiteSpace: "pre-wrap" }}
    />
  );
}

/** Render a card text field: an editable node in edit mode, else the static text
 *  (hidden when empty, matching the locked layout). */
function text(
  edit: CardEditHandlers | undefined,
  key: keyof CardFields,
  value: string,
  style: CSSProperties,
  placeholder: string,
): ReactElement | null {
  if (edit) {
    return (
      <EditableText
        fieldKey={key}
        initial={value}
        style={style}
        placeholder={placeholder}
        onEdit={edit.onEdit}
      />
    );
  }
  return value ? <div style={style}>{value}</div> : null;
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
  const { fields, brand, imageSrc, attribution, edit } = props;
  const c = cardColors(brand, props.accentHex);
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
        {text(
          edit,
          "eyebrow",
          fields.eyebrow,
          { ...eyebrowStyle(c.accent, body), marginBottom: 22 },
          "Eyebrow",
        )}
        {text(
          edit,
          "headline",
          fields.headline,
          {
            fontFamily: heading,
            fontSize: headlineSize("photo-led", fields.headline),
            fontWeight: 700,
            lineHeight: 1.04,
            color: c.paper,
          },
          "Headline",
        )}
        {text(
          edit,
          "body",
          fields.body,
          {
            fontFamily: body,
            fontSize: 30,
            lineHeight: 1.4,
            color: c.paper,
            opacity: 0.9,
            marginTop: 26,
          },
          "Body",
        )}
        <Footer
          cta={fields.cta}
          hashtag={fields.hashtag}
          color={c.paper}
          accent={c.accent}
          body={body}
          edit={edit}
        />
      </div>
      {attribution ? attributionEl(attribution, c.paper, body) : null}
    </div>
  );
}

function Statement(props: CardElementProps): ReactElement {
  const { fields, brand, edit } = props;
  const c = cardColors(brand, props.accentHex);
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
        {text(edit, "eyebrow", fields.eyebrow, eyebrowStyle(c.accent, body), "Eyebrow")}
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
        {text(
          edit,
          "headline",
          fields.headline,
          {
            fontFamily: heading,
            fontSize: headlineSize("statement", fields.headline),
            fontWeight: 700,
            lineHeight: 1.02,
            color: c.paper,
          },
          "Headline",
        )}
        {text(
          edit,
          "body",
          fields.body,
          {
            fontFamily: body,
            fontSize: 30,
            lineHeight: 1.45,
            color: c.paper,
            opacity: 0.82,
            marginTop: 34,
          },
          "Body",
        )}
      </div>
      <Footer
        cta={fields.cta}
        hashtag={fields.hashtag}
        color={c.paper}
        accent={c.accent}
        body={body}
        edit={edit}
      />
    </div>
  );
}

function Quote(props: CardElementProps): ReactElement {
  const { fields, brand, edit } = props;
  const c = cardColors(brand, props.accentHex);
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
        {text(
          edit,
          "eyebrow",
          fields.eyebrow,
          { ...eyebrowStyle(c.accent, body), marginBottom: 8 },
          "Eyebrow",
        )}
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
      {text(
        edit,
        "headline",
        fields.headline,
        {
          fontFamily: heading,
          fontSize: headlineSize("quote", fields.headline),
          fontWeight: 400,
          lineHeight: 1.16,
          color: c.ink,
          marginTop: -40,
        },
        "Headline",
      )}
      <div style={{ display: "flex", flexDirection: "column" }}>
        {text(
          edit,
          "body",
          fields.body,
          { fontFamily: body, fontSize: 27, color: c.ink, opacity: 0.75, marginBottom: 18 },
          "Body",
        )}
        <Footer
          cta={fields.cta}
          hashtag={fields.hashtag}
          color={c.ink}
          accent={c.accent}
          body={body}
          edit={edit}
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
  edit,
}: {
  cta: string;
  hashtag: string;
  color: string;
  accent: string;
  body: string;
  edit?: CardEditHandlers;
}): ReactElement | null {
  // Locked render hides an empty footer; edit mode always shows both fields so
  // they can be filled in.
  if (!edit && !cta && !hashtag) return null;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginTop: 38,
      }}
    >
      {text(
        edit,
        "cta",
        cta,
        { fontFamily: body, fontSize: 28, fontWeight: 600, color },
        "Call to action",
      ) ?? <div />}
      {text(
        edit,
        "hashtag",
        hashtag,
        { fontFamily: body, fontSize: 26, color: accent },
        "#hashtag",
      )}
    </div>
  );
}

export function buildCardElement(props: CardElementProps): ReactElement {
  // Sanitize once here so every render path (preview, export, history thumbnail)
  // is glyph-safe. While editing, keep the user's raw text so the caret/content
  // isn't mutated mid-keystroke; the locked preview + export re-clean on save.
  const safe: CardElementProps = props.edit
    ? props
    : { ...props, fields: cleanFields(props.fields) };
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
