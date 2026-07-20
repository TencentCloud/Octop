/** Built-in expert quick-card chip colors (keep market icons on the same look). */
export const QUICK_CARD_PASTEL_COLORS = [
  "#e8f4ff",
  "#dcfce7",
  "#fef3c7",
  "#fce7f3",
  "#f1f5f9",
  "#eef2ff",
  "#ecfeff",
  "#fff1f2",
] as const;

function isSoftPastel(color: string): boolean {
  const match = /^#([0-9a-fA-F]{6})$/.exec(color.trim());
  if (!match) return false;
  const value = Number.parseInt(match[1], 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  return luminance >= 0.82 && Math.min(r, g, b) >= 190;
}

/**
 * Use built-in pastel chips when possible.
 * Dark/saturated market colors are snapped onto the shared pastel palette.
 */
export function pastelIconBackground(
  color: string | null | undefined,
  index = 0,
  fallback = QUICK_CARD_PASTEL_COLORS[0],
): string {
  const raw = (color || "").trim();
  if (isSoftPastel(raw)) {
    return `#${raw.slice(1).toLowerCase()}`;
  }
  const palette = QUICK_CARD_PASTEL_COLORS;
  if (Number.isFinite(index) && index >= 0) {
    return palette[index % palette.length];
  }
  return fallback;
}
