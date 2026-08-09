import {
  DEFAULT_PALETTE,
  LEGACY_PALETTE_STORAGE_KEY,
  THEME_STORAGE_KEY,
  VALID_PALETTES,
  type ThemePalette,
} from "./themePalettes";

export type ThemePreference = "system" | "light" | "dark";

export type StoredAppearance = {
  preference: ThemePreference;
  palette: ThemePalette;
};

const VALID_PREFERENCES: ThemePreference[] = ["system", "light", "dark"];

function isPreference(value: unknown): value is ThemePreference {
  return (
    typeof value === "string" && (VALID_PREFERENCES as string[]).includes(value)
  );
}

function isPalette(value: unknown): value is ThemePalette {
  return (
    typeof value === "string" && (VALID_PALETTES as string[]).includes(value)
  );
}

function readLegacyPalette(): ThemePalette {
  const stored = localStorage.getItem(LEGACY_PALETTE_STORAGE_KEY);
  if (isPalette(stored)) return stored;
  return DEFAULT_PALETTE;
}

/**
 * Read light/dark preference + brand palette from the shared `theme` key.
 * Migrates legacy plain-string `theme` and `octop:ui-palette` values.
 */
export function readStoredAppearance(): StoredAppearance {
  const raw = localStorage.getItem(THEME_STORAGE_KEY);
  if (!raw) {
    return { preference: "system", palette: readLegacyPalette() };
  }

  // Legacy: plain preference string
  if (isPreference(raw)) {
    return { preference: raw, palette: readLegacyPalette() };
  }

  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      const obj = parsed as Record<string, unknown>;
      const preference = isPreference(obj.preference)
        ? obj.preference
        : "system";
      const palette = isPalette(obj.palette)
        ? obj.palette
        : readLegacyPalette();
      return { preference, palette };
    }
  } catch {
    // fall through
  }

  return { preference: "system", palette: readLegacyPalette() };
}

/** Persist both fields under the same `theme` key; drop legacy palette key. */
export function writeStoredAppearance(appearance: StoredAppearance): void {
  localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(appearance));
  localStorage.removeItem(LEGACY_PALETTE_STORAGE_KEY);
}

/** One-shot boot read + migrate for ThemeProvider initial state. */
export function loadAppearanceOnBoot(): StoredAppearance {
  const appearance = readStoredAppearance();
  writeStoredAppearance(appearance);
  return appearance;
}
