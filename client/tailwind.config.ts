import type { Config } from "tailwindcss";

/**
 * Folio design tokens — source of truth is docs/DESIGN.md (a living reference;
 * see docs/DECISIONS.md #18). Colors reference CSS variables in src/index.css
 * (:root / .dark) so components never hardcode hex.
 */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background) / <alpha-value>)",
        foreground: "hsl(var(--foreground) / <alpha-value>)",
        surface: {
          DEFAULT: "hsl(var(--surface) / <alpha-value>)",
          variant: "hsl(var(--surface-variant) / <alpha-value>)",
        },
        card: {
          DEFAULT: "hsl(var(--surface) / <alpha-value>)",
          foreground: "hsl(var(--foreground) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "hsl(var(--surface-variant) / <alpha-value>)",
          foreground: "hsl(var(--muted-foreground) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "hsl(var(--accent) / <alpha-value>)",
          strong: "hsl(var(--accent-strong) / <alpha-value>)",
          foreground: "hsl(var(--accent-foreground) / <alpha-value>)",
        },
        primary: {
          DEFAULT: "hsl(var(--accent) / <alpha-value>)",
          foreground: "hsl(var(--accent-foreground) / <alpha-value>)",
        },
        border: "hsl(var(--border) / <alpha-value>)",
        input: "hsl(var(--border) / <alpha-value>)",
        ring: "hsl(var(--ring) / <alpha-value>)",
        success: "hsl(var(--success) / <alpha-value>)",
        warning: "hsl(var(--warning) / <alpha-value>)",
        destructive: {
          DEFAULT: "hsl(var(--destructive) / <alpha-value>)",
          foreground: "hsl(var(--destructive-foreground) / <alpha-value>)",
        },
        // Card-preview surround on the Generate page (the only surface darker
        // than background in light mode). DESIGN.md §1.
        "preview-bg": "hsl(var(--preview-bg) / <alpha-value>)",
        popover: {
          DEFAULT: "hsl(var(--surface) / <alpha-value>)",
          foreground: "hsl(var(--foreground) / <alpha-value>)",
        },
      },
      fontFamily: {
        // App chrome only — the card preview uses the WORKSPACE's brand fonts.
        sans: ["Plus Jakarta Sans", "system-ui", "sans-serif"],
        display: ["Plus Jakarta Sans", "system-ui", "sans-serif"],
        mono: ["DM Mono", "ui-monospace", "monospace"],
      },
      // Sub-`xs` micro sizes for mono eyebrows / badges / data labels. The main
      // DESIGN.md §2 rem type-scale (0.75…3rem) already equals Tailwind's
      // xs…5xl defaults, so only the below-scale sizes need naming. Size-only (no
      // line-height) so they swap 1:1 for the arbitrary text-[10px]/[9px] values.
      fontSize: {
        "2xs": "0.625rem", // 10px — the canonical eyebrow/label size
        "3xs": "0.5625rem", // 9px — tiny badges
      },
      letterSpacing: {
        // DESIGN.md §2: one eyebrow tracking; headings tighten -0.01 to -0.015em.
        eyebrow: "0.12em",
        heading: "-0.01em",
        display: "-0.015em",
      },
      borderRadius: {
        sm: "6px",
        md: "8px",
        lg: "12px",
        xl: "16px",
      },
      boxShadow: {
        light: "0 1px 2px rgb(26 29 33 / 0.04), 0 2px 6px rgb(26 29 33 / 0.05)",
        medium: "0 4px 12px rgb(26 29 33 / 0.08)",
        heavy: "0 12px 32px rgb(26 29 33 / 0.12)",
        accent: "0 8px 24px rgb(194 24 91 / 0.22)",
        preview: "0 8px 32px rgb(26 29 33 / 0.18)",
      },
      zIndex: {
        header: "10",
        dropdown: "20",
        drawer: "40",
        picker: "60",
        modal: "100",
        toast: "1000",
      },
      keyframes: {
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) both",
        // Image picker panel (DESIGN §5): slides in from the right, 250ms ease-out.
        "slide-in-right": "slide-in-right 0.25s ease-out both",
        "fade-in": "fade-in 0.2s ease-out both",
      },
    },
  },
  plugins: [],
} satisfies Config;
