/**
 * Stat-card and chart-axis figures for token usage.
 * Counts that still fit a 22px card stay exact. From about one million
 * the card shows a compact unit, and the exact grouped number sits under it.
 */

/** ~7 grouped digits still fit; 1,000,000 (9 chars at 22px) does not. */
const COMPACT_FROM = 1_000_000;

const ZH_UNITS = [
  { value: 1e12, suffix: "万亿" },
  { value: 1e8, suffix: "亿" },
  { value: 1e4, suffix: "万" },
] as const;

const EN_UNITS = [
  { value: 1e12, suffix: "T" },
  { value: 1e9, suffix: "B" },
  { value: 1e6, suffix: "M" },
] as const;

function intlTag(locale: string): string {
  return locale.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

function isZh(locale: string): boolean {
  return locale.toLowerCase().startsWith("zh");
}

/** Grouped exact count, e.g. 2788473 → "2,788,473". */
export function formatExactCount(n: number, locale: string): string {
  if (!Number.isFinite(n)) return "0";
  return n.toLocaleString(intlTag(locale), {
    maximumFractionDigits: Number.isInteger(n) ? 0 : 1,
  });
}

function trimScaled(scaled: number): string {
  const digits = scaled >= 1000 ? 0 : scaled >= 10 ? 1 : 2;
  return scaled
    .toFixed(digits)
    .replace(/\.0+$/, "")
    .replace(/(\.\d*[1-9])0+$/, "$1");
}

function formatWithUnits(
  abs: number,
  units: readonly { value: number; suffix: string }[],
): string {
  for (let i = 0; i < units.length; i++) {
    const unit = units[i];
    if (abs < unit.value) continue;
    const text = trimScaled(abs / unit.value);
    if (Number(text) >= 1000 && i > 0) {
      const promoted = trimScaled(abs / units[i - 1].value);
      if (Number(promoted) >= 1) {
        return promoted + units[i - 1].suffix;
      }
    }
    return text + unit.suffix;
  }
  return trimScaled(abs);
}

/**
 * Compact label once the full figure no longer fits a stat card.
 * zh: 278.8万 / 1.23亿. en: 2.79M / 1.23B.
 */
export function formatCompactCount(n: number, locale: string): string {
  if (!Number.isFinite(n)) return "0";
  const abs = Math.abs(n);
  if (abs < COMPACT_FROM) return formatExactCount(n, locale);
  const text = formatWithUnits(abs, isZh(locale) ? ZH_UNITS : EN_UNITS);
  return n < 0 ? `-${text}` : text;
}

/** Card text, plus the exact figure shown under it when abbreviated. */
export function usageCountDisplay(
  n: number,
  locale: string,
): { value: string; exact?: string } {
  const exact = formatExactCount(n, locale);
  const value = formatCompactCount(n, locale);
  return value === exact ? { value } : { value, exact };
}
