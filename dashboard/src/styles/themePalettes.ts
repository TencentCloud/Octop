/** Brand palettes — orthogonal to light/dark mode (`data-theme`). */

export type ThemePalette =
  | "rose"
  | "tech"
  | "indigo"
  | "teal"
  | "violet"
  | "emerald"
  | "amber"
  | "slate"
  | "custom";

export const VALID_PALETTES: ThemePalette[] = [
  "rose",
  "tech",
  "indigo",
  "teal",
  "violet",
  "emerald",
  "amber",
  "slate",
];

/** Curated palettes only — "custom" is handled separately via a hex value. */
export const CURATED_PALETTES: ThemePalette[] = [...VALID_PALETTES];

export const DEFAULT_PALETTE: ThemePalette = "rose";
export const DEFAULT_CUSTOM_COLOR = "#4B74FA";

/** Shared localStorage key for light/dark preference + brand palette. */
export const THEME_STORAGE_KEY = "theme";

/** Legacy palette-only key; migrated into {@link THEME_STORAGE_KEY}.palette. */
export const LEGACY_PALETTE_STORAGE_KEY = "octop:ui-palette";

/** @deprecated Use {@link LEGACY_PALETTE_STORAGE_KEY}; kept for import compatibility. */
export const PALETTE_STORAGE_KEY = LEGACY_PALETTE_STORAGE_KEY;

/** Swatch color shown in the palette picker (light brand). */
export const PALETTE_SWATCH: Record<ThemePalette, string> = {
  rose: "#E85D75",
  tech: "#4B74FA",
  indigo: "#6366F1",
  teal: "#0D9488",
  violet: "#7C3AED",
  emerald: "#10B981",
  amber: "#F59E0B",
  slate: "#64748B",
  custom: DEFAULT_CUSTOM_COLOR, // live swatch is provided by the picker UI
};

type AntdBrandTokens = {
  colorPrimary: string;
  colorPrimaryHover: string;
  colorPrimaryActive: string;
  colorLink: string;
  colorPrimaryBg?: string;
  colorPrimaryBgHover?: string;
  colorPrimaryBorder?: string;
  colorPrimaryBorderHover?: string;
  colorPrimaryText?: string;
  colorPrimaryTextHover?: string;
  colorPrimaryTextActive?: string;
};

/** Ant Design primary tokens per curated palette × mode ("custom" derives at runtime). */
export const ANTD_BRAND_TOKENS: Record<
  Exclude<ThemePalette, "custom">,
  { light: AntdBrandTokens; dark: AntdBrandTokens }
> = {
  rose: {
    light: {
      colorPrimary: "#E85D75",
      colorPrimaryHover: "#D14A62",
      colorPrimaryActive: "#B83A50",
      colorLink: "#E85D75",
    },
    dark: {
      colorPrimary: "#F08B9A",
      colorPrimaryBg: "rgba(232, 93, 117, 0.12)",
      colorPrimaryBgHover: "rgba(232, 93, 117, 0.16)",
      colorPrimaryBorder: "rgba(232, 93, 117, 0.25)",
      colorPrimaryBorderHover: "rgba(232, 93, 117, 0.35)",
      colorPrimaryHover: "#F5A8B4",
      colorPrimaryActive: "#E85D75",
      colorPrimaryText: "#F08B9A",
      colorPrimaryTextHover: "#F5A8B4",
      colorPrimaryTextActive: "#E85D75",
      colorLink: "#F08B9A",
    },
  },
  tech: {
    light: {
      colorPrimary: "#3A5FE0",
      colorPrimaryHover: "#2E4FD4",
      colorPrimaryActive: "#233FB8",
      colorLink: "#3A5FE0",
    },
    dark: {
      colorPrimary: "#3A5FE0",
      colorPrimaryBg: "rgba(75, 116, 250, 0.14)",
      colorPrimaryBgHover: "rgba(75, 116, 250, 0.2)",
      colorPrimaryBorder: "rgba(75, 116, 250, 0.3)",
      colorPrimaryBorderHover: "rgba(75, 116, 250, 0.4)",
      colorPrimaryHover: "#2E4FD4",
      colorPrimaryActive: "#233FB8",
      colorPrimaryText: "#7B9BFC",
      colorPrimaryTextHover: "#9BB4FD",
      colorPrimaryTextActive: "#4B74FA",
      colorLink: "#7B9BFC",
    },
  },
  indigo: {
    light: {
      colorPrimary: "#4F46E5",
      colorPrimaryHover: "#4338CA",
      colorPrimaryActive: "#3730A3",
      colorLink: "#4F46E5",
    },
    dark: {
      colorPrimary: "#4F46E5",
      colorPrimaryBg: "rgba(99, 102, 241, 0.14)",
      colorPrimaryBgHover: "rgba(99, 102, 241, 0.2)",
      colorPrimaryBorder: "rgba(99, 102, 241, 0.3)",
      colorPrimaryBorderHover: "rgba(99, 102, 241, 0.4)",
      colorPrimaryHover: "#4338CA",
      colorPrimaryActive: "#3730A3",
      colorPrimaryText: "#818CF8",
      colorPrimaryTextHover: "#A5B4FC",
      colorPrimaryTextActive: "#6366F1",
      colorLink: "#818CF8",
    },
  },
  teal: {
    light: {
      colorPrimary: "#0F766E",
      colorPrimaryHover: "#115E59",
      colorPrimaryActive: "#134E4A",
      colorLink: "#0F766E",
    },
    dark: {
      colorPrimary: "#0F766E",
      colorPrimaryBg: "rgba(13, 148, 136, 0.14)",
      colorPrimaryBgHover: "rgba(13, 148, 136, 0.2)",
      colorPrimaryBorder: "rgba(13, 148, 136, 0.3)",
      colorPrimaryBorderHover: "rgba(13, 148, 136, 0.4)",
      colorPrimaryHover: "#115E59",
      colorPrimaryActive: "#134E4A",
      colorPrimaryText: "#2DD4BF",
      colorPrimaryTextHover: "#5EEAD4",
      colorPrimaryTextActive: "#0D9488",
      colorLink: "#2DD4BF",
    },
  },
  violet: {
    light: {
      colorPrimary: "#7C3AED",
      colorPrimaryHover: "#6D28D9",
      colorPrimaryActive: "#5B21B6",
      colorLink: "#7C3AED",
    },
    dark: {
      colorPrimary: "#7C3AED",
      colorPrimaryBg: "rgba(124, 58, 237, 0.14)",
      colorPrimaryBgHover: "rgba(124, 58, 237, 0.2)",
      colorPrimaryBorder: "rgba(124, 58, 237, 0.3)",
      colorPrimaryBorderHover: "rgba(124, 58, 237, 0.4)",
      colorPrimaryHover: "#6D28D9",
      colorPrimaryActive: "#5B21B6",
      colorPrimaryText: "#A78BFA",
      colorPrimaryTextHover: "#C4B5FD",
      colorPrimaryTextActive: "#7C3AED",
      colorLink: "#A78BFA",
    },
  },
  emerald: {
    light: {
      colorPrimary: "#047857",
      colorPrimaryHover: "#065F46",
      colorPrimaryActive: "#064E3B",
      colorLink: "#047857",
    },
    dark: {
      colorPrimary: "#047857",
      colorPrimaryBg: "rgba(16, 185, 129, 0.14)",
      colorPrimaryBgHover: "rgba(16, 185, 129, 0.2)",
      colorPrimaryBorder: "rgba(16, 185, 129, 0.3)",
      colorPrimaryBorderHover: "rgba(16, 185, 129, 0.4)",
      colorPrimaryHover: "#065F46",
      colorPrimaryActive: "#064E3B",
      colorPrimaryText: "#34D399",
      colorPrimaryTextHover: "#6EE7B7",
      colorPrimaryTextActive: "#10B981",
      colorLink: "#34D399",
    },
  },
  amber: {
    light: {
      colorPrimary: "#B45309",
      colorPrimaryHover: "#92400E",
      colorPrimaryActive: "#78350F",
      colorLink: "#B45309",
    },
    dark: {
      colorPrimary: "#B45309",
      colorPrimaryBg: "rgba(245, 158, 11, 0.14)",
      colorPrimaryBgHover: "rgba(245, 158, 11, 0.2)",
      colorPrimaryBorder: "rgba(245, 158, 11, 0.3)",
      colorPrimaryBorderHover: "rgba(245, 158, 11, 0.4)",
      colorPrimaryHover: "#92400E",
      colorPrimaryActive: "#78350F",
      colorPrimaryText: "#FBBF24",
      colorPrimaryTextHover: "#FCD34D",
      colorPrimaryTextActive: "#F59E0B",
      colorLink: "#FBBF24",
    },
  },
  slate: {
    light: {
      colorPrimary: "#475569",
      colorPrimaryHover: "#334155",
      colorPrimaryActive: "#1E293B",
      colorLink: "#475569",
    },
    dark: {
      colorPrimary: "#475569",
      colorPrimaryBg: "rgba(100, 116, 139, 0.18)",
      colorPrimaryBgHover: "rgba(100, 116, 139, 0.24)",
      colorPrimaryBorder: "rgba(148, 163, 184, 0.3)",
      colorPrimaryBorderHover: "rgba(148, 163, 184, 0.4)",
      colorPrimaryHover: "#334155",
      colorPrimaryActive: "#1E293B",
      colorPrimaryText: "#94A3B8",
      colorPrimaryTextHover: "#CBD5E1",
      colorPrimaryTextActive: "#64748B",
      colorLink: "#94A3B8",
    },
  },
};

/** Resolved Ant Design / chart primary for the active palette × mode. */
export function brandPrimary(
  palette: ThemePalette,
  isDark: boolean,
  customColor?: string | null,
): string {
  const tokens = brandTokensFor(palette, isDark, customColor);
  return isDark ? tokens.colorLink : tokens.colorPrimary;
}

// ---------------------------------------------------------------------------
// Custom brand color — derive the full token/CSS-variable set from one hex
// ---------------------------------------------------------------------------

/** Normalize user input (#abc / abc / #aabbcc / rgb-free hex) to #rrggbb. */
export function normalizeHexColor(
  input: string | null | undefined,
): string | null {
  const raw = (input ?? "").trim().replace(/^#/, "");
  if (/^[0-9a-fA-F]{3}$/.test(raw)) {
    return `#${raw
      .split("")
      .map((ch) => `${ch}${ch}`)
      .join("")
      .toLowerCase()}`;
  }
  if (/^[0-9a-fA-F]{6}$/.test(raw)) {
    return `#${raw.toLowerCase()}`;
  }
  return null;
}

function hexToRgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex(r: number, g: number, b: number): string {
  const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
  return `#${((clamp(r) << 16) | (clamp(g) << 8) | clamp(b))
    .toString(16)
    .padStart(6, "0")}`;
}

/** Linear interpolation between two hex colors (t in [0,1]). */
export function mixHex(a: string, b: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(a);
  const [r2, g2, b2] = hexToRgb(b);
  return rgbToHex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t);
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((c) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two hex colors (1..21). */
export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const lighter = Math.max(la, lb);
  const darker = Math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}

/** Darken until white text reaches ≥4.5:1 (WCAG AA); never below 12% lightness. */
function ensureSolidOnWhite(hex: string): string {
  let color = hex;
  for (let i = 0; i < 10 && contrastRatio(color, "#FFFFFF") < 4.5; i++) {
    color = mixHex(color, "#000000", 0.08);
  }
  return color;
}

/** Lighten until readable on dark surfaces (≥3:1 against #0f1117). */
function ensureTextOnDark(hex: string): string {
  let color = hex;
  for (let i = 0; i < 12 && contrastRatio(color, "#0f1117") < 3; i++) {
    color = mixHex(color, "#FFFFFF", 0.12);
  }
  return color;
}

export interface CustomBrandColors {
  /** Darkened solid primary, readable with white text (light mode). */
  solid: string;
  /** Brightened text/link variant for dark mode. */
  onDark: string;
  /** Accent variant for badges/tags (original hue, mid luminance). */
  accent: string;
}

export function deriveCustomBrandColors(hex: string): CustomBrandColors {
  return {
    solid: ensureSolidOnWhite(hex),
    onDark: ensureTextOnDark(hex),
    accent: ensureTextOnDark(mixHex(hex, "#FFFFFF", 0.12)),
  };
}

/** Ant Design brand tokens for the custom palette, derived from one hex. */
export function customBrandTokens(hex: string): {
  light: AntdBrandTokens;
  dark: AntdBrandTokens;
} {
  const { solid, onDark } = deriveCustomBrandColors(hex);
  const solidHover = mixHex(solid, "#000000", 0.1);
  const solidActive = mixHex(solid, "#000000", 0.2);
  return {
    light: {
      colorPrimary: solid,
      colorPrimaryHover: solidHover,
      colorPrimaryActive: solidActive,
      colorLink: solid,
    },
    dark: {
      colorPrimary: solid,
      colorPrimaryBg: `rgba(${hexToRgb(solid).join(", ")}, 0.12)`,
      colorPrimaryBgHover: `rgba(${hexToRgb(solid).join(", ")}, 0.16)`,
      colorPrimaryBorder: `rgba(${hexToRgb(solid).join(", ")}, 0.25)`,
      colorPrimaryBorderHover: `rgba(${hexToRgb(solid).join(", ")}, 0.35)`,
      colorPrimaryHover: mixHex(onDark, "#FFFFFF", 0.12),
      colorPrimaryActive: solid,
      colorPrimaryText: onDark,
      colorPrimaryTextHover: mixHex(onDark, "#FFFFFF", 0.18),
      colorPrimaryTextActive: onDark,
      colorLink: onDark,
    },
  };
}

/** Resolve Ant tokens for any palette — "custom" derives from the stored hex. */
export function brandTokensFor(
  palette: ThemePalette,
  isDark: boolean,
  customColor?: string | null,
): AntdBrandTokens {
  if (palette === "custom") {
    return customBrandTokens(customColor || DEFAULT_CUSTOM_COLOR)[
      isDark ? "dark" : "light"
    ];
  }
  return ANTD_BRAND_TOKENS[palette][isDark ? "dark" : "light"];
}

/**
 * CSS custom-property overrides for `html[data-palette="custom"]`.
 * Mirrors the curated palette blocks in theme-vars.css but derived at runtime.
 */
export function customPaletteCssVars(hex: string, isDark: boolean): string {
  const { solid, onDark, accent } = deriveCustomBrandColors(hex);
  const rgb = hexToRgb(solid).join(", ");
  const rgbOnDark = hexToRgb(onDark).join(", ");
  if (isDark) {
    return `html[data-palette="custom"][data-theme="dark"]{
--fn-bg-hover: rgba(${rgb}, 0.1);
--fn-bg-active: rgba(${rgb}, 0.16);
--fn-bg-selected: rgba(${rgb}, 0.12);
--fn-text-brand: ${onDark};
--fn-logo-color: ${onDark};
--fn-border-focus: ${onDark};
--fn-color-brand: ${solid};
--fn-color-brand-hover: ${mixHex(solid, "#000000", 0.1)};
--fn-color-brand-soft: ${mixHex(solid, "#000000", 0.1)};
--fn-color-brand-bg: rgba(${rgb}, 0.14);
--fn-color-brand-light: rgba(${rgb}, 0.18);
--fn-color-brand-shadow: rgba(${rgb}, 0.28);
--fn-color-brand-glow: rgba(${rgb}, 0.1);
--fn-assistant-bubble-bg-gradient: linear-gradient(135deg, rgba(${rgbOnDark}, 0.12) 0%, rgba(255, 255, 255, 0.04) 50%, rgba(${rgbOnDark}, 0.08) 100%);
--fn-assistant-bubble-border: rgba(${rgbOnDark}, 0.16);
--fn-assistant-glow-color: ${rgbOnDark};
--fn-tag-channel-text: ${onDark};
--fn-shadow-brand: 0 4px 14px rgba(${rgb}, 0.24);
--fn-shadow-brand-lg: 0 8px 24px rgba(${rgb}, 0.32);
--fn-row-selected-bg: rgba(${rgb}, 0.12);
--fn-row-selected-hover: rgba(${rgb}, 0.18);
--fn-row-selected-alt-bg: rgba(${rgb}, 0.1);
--fn-row-selected-alt-hover: rgba(${rgb}, 0.15);
--fn-row-selected-border: ${onDark};
--fn-sidebar-item-active-bg: rgba(${rgb}, 0.16);
--fn-sidebar-item-active: rgba(${rgb}, 0.16);
--fn-sidebar-item-active-text: ${onDark};
}`;
  }
  return `html[data-palette="custom"]:not([data-theme="dark"]){
--fn-bg-hover: rgba(${rgb}, 0.04);
--fn-bg-active: rgba(${rgb}, 0.08);
--fn-bg-selected: rgba(${rgb}, 0.06);
--fn-text-brand: ${solid};
--fn-logo-color: ${solid};
--fn-border-focus: ${solid};
--fn-color-brand: ${solid};
--fn-color-brand-hover: ${mixHex(solid, "#000000", 0.1)};
--fn-color-brand-soft: ${mixHex(solid, "#000000", 0.1)};
--fn-color-brand-bg: rgba(${rgb}, 0.06);
--fn-color-brand-light: ${mixHex(solid, "#FFFFFF", 0.88)};
--fn-color-brand-shadow: rgba(${rgb}, 0.15);
--fn-color-brand-glow: rgba(${rgb}, 0.08);
--fn-assistant-bubble-bg-gradient: linear-gradient(135deg, ${mixHex(
    solid,
    "#FFFFFF",
    0.9,
  )} 0%, rgba(255, 255, 255, 0.35) 50%, ${mixHex(solid, "#FFFFFF", 0.82)} 100%);
--fn-assistant-bubble-border: rgba(${rgb}, 0.12);
--fn-assistant-glow-color: ${rgb};
--fn-tag-channel-text: ${accent};
--fn-shadow-brand: 0 4px 14px rgba(${rgb}, 0.18);
--fn-shadow-brand-lg: 0 8px 24px rgba(${rgb}, 0.24);
--fn-row-selected-bg: rgba(${rgb}, 0.05);
--fn-row-selected-hover: rgba(${rgb}, 0.09);
--fn-row-selected-alt-bg: rgba(${rgb}, 0.04);
--fn-row-selected-alt-hover: rgba(${rgb}, 0.08);
--fn-row-selected-border: ${solid};
--fn-sidebar-item-active-bg: ${mixHex(solid, "#FFFFFF", 0.92)};
--fn-sidebar-item-active: rgba(${rgb}, 0.08);
--fn-sidebar-item-active-text: ${solid};
}`;
}
