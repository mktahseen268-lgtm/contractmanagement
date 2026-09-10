/**
 * Contrast-safe branding (Phase 9, item 5 — WCAG 1.4.3).
 *
 * The brand accent is a single CSS variable a tenant can set to anything. The shipped default,
 * `#3e7bfa`, measures **3.88:1** against the white text on top of it — below the 4.5:1 that
 * normal-size text needs. Every primary button in the product failed on that one value.
 *
 * Darkening the default fixes the default and nothing else: the next tenant to pick a cheerful
 * brand colour breaks it again, and nobody will notice until an audit. So the accent used as a
 * *button background* is derived here — kept as chosen when it already passes, darkened only as
 * far as it must when it does not.
 *
 * The original colour is preserved separately for borders, icons and large text, where 3:1 is
 * the requirement and the brand should be recognisable. Only the surface that carries small
 * white text is adjusted.
 */

type Rgb = { r: number; g: number; b: number };

function parseHex(value: string): Rgb | null {
  const hex = (value || "").trim().replace(/^#/, "");
  const full =
    hex.length === 3
      ? hex
          .split("")
          .map((c) => c + c)
          .join("")
      : hex;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null;
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  };
}

function toHex({ r, g, b }: Rgb): string {
  const part = (n: number) =>
    Math.max(0, Math.min(255, Math.round(n)))
      .toString(16)
      .padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

/** Relative luminance, per WCAG 2.1 §relative-luminance. */
export function luminance(color: string): number {
  const rgb = parseHex(color);
  if (!rgb) return 0;
  const channel = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b);
}

/** Contrast ratio between two colours, 1 (identical) to 21 (black on white). */
export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Darken `color` just enough that white text on it reaches `target` (4.5:1 by default).
 *
 * Returns the colour unchanged when it already passes — the brand should only be altered when
 * leaving it alone would make the text unreadable, and "close enough" is not a thing WCAG has.
 *
 * The step is deliberately small (2%) so a colour that only just fails moves only just far
 * enough. Bisecting would be fewer iterations and a less predictable result; 50 steps of a
 * cheap multiply is nothing on a value computed once per page load.
 */
export function ensureContrastWithWhite(color: string, target = 4.5): string {
  const rgb = parseHex(color);
  if (!rgb) return color; // Unparseable: leave it. Guessing a brand colour is worse.
  if (contrastRatio(color, "#ffffff") >= target) return color;

  let current = { ...rgb };
  for (let i = 0; i < 50; i += 1) {
    current = { r: current.r * 0.98, g: current.g * 0.98, b: current.b * 0.98 };
    const hex = toHex(current);
    if (contrastRatio(hex, "#ffffff") >= target) return hex;
  }
  // Even black would pass, so this is unreachable in practice. Returning black rather than the
  // failing original keeps the guarantee unconditional.
  return "#000000";
}

/** A slightly darker shade, for the hover state of a button. */
export function darken(color: string, amount = 0.12): string {
  const rgb = parseHex(color);
  if (!rgb) return color;
  const f = 1 - Math.max(0, Math.min(1, amount));
  return toHex({ r: rgb.r * f, g: rgb.g * f, b: rgb.b * f });
}

/**
 * Apply a tenant's accent to the document, keeping white-on-accent text readable.
 *
 * `--color-accent` becomes the contrast-safe shade because it is what button backgrounds use.
 * `--color-accent-brand` keeps the colour exactly as chosen, for borders, icons and large text
 * where 3:1 applies and the brand should still look like itself.
 */
export function applyAccent(color: string | null | undefined): void {
  if (typeof document === "undefined" || !color) return;
  const safe = ensureContrastWithWhite(color);
  const root = document.documentElement.style;
  root.setProperty("--color-accent-brand", color);
  root.setProperty("--color-accent", safe);
  root.setProperty("--color-accent-hover", darken(safe));
}
