/** Brand palettes — orthogonal to light/dark mode (`data-theme`). */

export type ThemePalette = "rose" | "tech" | "emerald" | "amber" | "slate";

export const VALID_PALETTES: ThemePalette[] = [
  "rose",
  "tech",
  "emerald",
  "amber",
  "slate",
];

export const DEFAULT_PALETTE: ThemePalette = "rose";

export const PALETTE_STORAGE_KEY = "octop:ui-palette";

/** Swatch color shown in the palette picker (light brand). */
export const PALETTE_SWATCH: Record<ThemePalette, string> = {
  rose: "#E85D75",
  tech: "#4B74FA",
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
      colorPrimary: "#4B74FA",
      colorPrimaryHover: "#3A5FE0",
      colorPrimaryActive: "#2E4FD4",
      colorLink: "#4B74FA",
    },
    dark: {
      colorPrimary: "#7B9BFC",
      colorPrimaryBg: "rgba(75, 116, 250, 0.14)",
      colorPrimaryBgHover: "rgba(75, 116, 250, 0.2)",
      colorPrimaryBorder: "rgba(75, 116, 250, 0.3)",
      colorPrimaryBorderHover: "rgba(75, 116, 250, 0.4)",
      colorPrimaryHover: "#9BB4FD",
      colorPrimaryActive: "#4B74FA",
      colorPrimaryText: "#7B9BFC",
      colorPrimaryTextHover: "#9BB4FD",
      colorPrimaryTextActive: "#4B74FA",
      colorLink: "#7B9BFC",
    },
  },
  emerald: {
    light: {
      colorPrimary: "#10B981",
      colorPrimaryHover: "#059669",
      colorPrimaryActive: "#047857",
      colorLink: "#10B981",
    },
    dark: {
      colorPrimary: "#34D399",
      colorPrimaryBg: "rgba(16, 185, 129, 0.14)",
      colorPrimaryBgHover: "rgba(16, 185, 129, 0.2)",
      colorPrimaryBorder: "rgba(16, 185, 129, 0.3)",
      colorPrimaryBorderHover: "rgba(16, 185, 129, 0.4)",
      colorPrimaryHover: "#6EE7B7",
      colorPrimaryActive: "#10B981",
      colorPrimaryText: "#34D399",
      colorPrimaryTextHover: "#6EE7B7",
      colorPrimaryTextActive: "#10B981",
      colorLink: "#34D399",
    },
  },
  amber: {
    light: {
      colorPrimary: "#F59E0B",
      colorPrimaryHover: "#D97706",
      colorPrimaryActive: "#B45309",
      colorLink: "#D97706",
    },
    dark: {
      colorPrimary: "#FBBF24",
      colorPrimaryBg: "rgba(245, 158, 11, 0.14)",
      colorPrimaryBgHover: "rgba(245, 158, 11, 0.2)",
      colorPrimaryBorder: "rgba(245, 158, 11, 0.3)",
      colorPrimaryBorderHover: "rgba(245, 158, 11, 0.4)",
      colorPrimaryHover: "#FCD34D",
      colorPrimaryActive: "#F59E0B",
      colorPrimaryText: "#FBBF24",
      colorPrimaryTextHover: "#FCD34D",
      colorPrimaryTextActive: "#F59E0B",
      colorLink: "#FBBF24",
    },
  },
  slate: {
    light: {
      colorPrimary: "#64748B",
      colorPrimaryHover: "#475569",
      colorPrimaryActive: "#334155",
      colorLink: "#475569",
    },
    dark: {
      colorPrimary: "#94A3B8",
      colorPrimaryBg: "rgba(100, 116, 139, 0.18)",
      colorPrimaryBgHover: "rgba(100, 116, 139, 0.24)",
      colorPrimaryBorder: "rgba(148, 163, 184, 0.3)",
      colorPrimaryBorderHover: "rgba(148, 163, 184, 0.4)",
      colorPrimaryHover: "#CBD5E1",
      colorPrimaryActive: "#64748B",
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
): string {
  return ANTD_BRAND_TOKENS[palette][isDark ? "dark" : "light"].colorPrimary;
}
