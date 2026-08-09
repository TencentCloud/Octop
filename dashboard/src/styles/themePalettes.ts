/** Brand palettes — orthogonal to light/dark mode (`data-theme`). */

export type ThemePalette =
  | "rose"
  | "tech"
  | "indigo"
  | "teal"
  | "violet"
  | "emerald"
  | "amber"
  | "slate";

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

export const DEFAULT_PALETTE: ThemePalette = "rose";

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

/** Ant Design primary tokens per palette × mode. */
export const ANTD_BRAND_TOKENS: Record<
  ThemePalette,
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
export function brandPrimary(palette: ThemePalette, isDark: boolean): string {
  const tokens = ANTD_BRAND_TOKENS[palette][isDark ? "dark" : "light"];
  return isDark ? tokens.colorLink : tokens.colorPrimary;
}
