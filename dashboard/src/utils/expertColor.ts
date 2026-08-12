import {
  DEFAULT_PALETTE,
  PALETTE_SWATCH,
  VALID_PALETTES,
  type ThemePalette,
} from "../styles/themePalettes";

function parseHex(color: string): [number, number, number] | null {
  const raw = color.trim().replace(/^#/, "");
  if (!/^[0-9a-fA-F]{6}$/.test(raw) && !/^[0-9a-fA-F]{3}$/.test(raw)) {
    return null;
  }
  const hex =
    raw.length === 3
      ? raw
          .split("")
          .map((ch) => `${ch}${ch}`)
          .join("")
      : raw;
  return [
    Number.parseInt(hex.slice(0, 2), 16),
    Number.parseInt(hex.slice(2, 4), 16),
    Number.parseInt(hex.slice(4, 6), 16),
  ];
}

function colorDistance(
  a: [number, number, number],
  b: [number, number, number],
): number {
  const dr = a[0] - b[0];
  const dg = a[1] - b[1];
  const db = a[2] - b[2];
  return dr * dr + dg * dg + db * db;
}

/** Map a stored expert hex (or null) onto the curated 8-swatch palette. */
export function resolveExpertPalette(
  color: string | null | undefined,
): ThemePalette {
  if (!color) return DEFAULT_PALETTE;
  const normalized = color.trim().toLowerCase();
  for (const key of VALID_PALETTES) {
    if (PALETTE_SWATCH[key].toLowerCase() === normalized) {
      return key;
    }
  }
  const rgb = parseHex(normalized);
  if (!rgb) return DEFAULT_PALETTE;

  let best: ThemePalette = DEFAULT_PALETTE;
  let bestDist = Number.POSITIVE_INFINITY;
  for (const key of VALID_PALETTES) {
    const swatch = parseHex(PALETTE_SWATCH[key]);
    if (!swatch) continue;
    const dist = colorDistance(rgb, swatch);
    if (dist < bestDist) {
      best = key;
      bestDist = dist;
    }
  }
  return best;
}

export function expertPaletteColor(palette: ThemePalette): string {
  return PALETTE_SWATCH[palette];
}
