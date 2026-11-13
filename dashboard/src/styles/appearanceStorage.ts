import {
  DEFAULT_CUSTOM_COLOR,
  DEFAULT_PALETTE,
  LEGACY_PALETTE_STORAGE_KEY,
  THEME_STORAGE_KEY,
  VALID_PALETTES,
  normalizeHexColor,
  type ThemePalette,
} from "./themePalettes";

export type ThemePreference = "system" | "light" | "dark";

export type StoredAppearance = {
  preference: ThemePreference;
  palette: ThemePalette;
  /** Brand hex for the "custom" palette; ignored for curated palettes. */
  customColor?: string;
};

const VALID_PREFERENCES: ThemePreference[] = ["system", "light", "dark"];

function isPreference(value: unknown): value is ThemePreference {
  return (
    typeof value === "string" && (VALID_PREFERENCES as string[]).includes(value)
  );
}

function isPalette(value: unknown): value is ThemePalette {
  return (
    typeof value === "string" &&
    ([...VALID_PALETTES, "custom"] as string[]).includes(value)
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
export function readStoredAppearance(userId?: number | null): StoredAppearance {
  if (typeof userId === "number") {
    const own = localStorage.getItem(userAppearanceStorageKey(userId));
    if (!own) return defaultAppearance();
    return parseUserAppearance(own);
  }
  const raw = localStorage.getItem(THEME_STORAGE_KEY);
  if (!raw) {
    return {
      preference: "system",
      palette: readLegacyPalette(),
      customColor: DEFAULT_CUSTOM_COLOR,
    };
  }

  // Legacy: plain preference string
  if (isPreference(raw)) {
    return {
      preference: raw,
      palette: readLegacyPalette(),
      customColor: DEFAULT_CUSTOM_COLOR,
    };
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
      const customColor =
        normalizeHexColor(obj.customColor as string) ?? DEFAULT_CUSTOM_COLOR;
      return { preference, palette, customColor };
    }
  } catch {
    // fall through
  }

  return {
    preference: "system",
    palette: readLegacyPalette(),
    customColor: DEFAULT_CUSTOM_COLOR,
  };
}

function parseUserAppearance(raw: string): StoredAppearance {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      const obj = parsed as Record<string, unknown>;
      return {
        preference: isPreference(obj.preference) ? obj.preference : "system",
        palette: isPalette(obj.palette) ? obj.palette : DEFAULT_PALETTE,
        customColor:
          normalizeHexColor(obj.customColor as string) ?? DEFAULT_CUSTOM_COLOR,
      };
    }
  } catch {
    // fall through
  }
  return defaultAppearance();
}

export function defaultAppearance(): StoredAppearance {
  return {
    preference: "system",
    palette: DEFAULT_PALETTE,
    customColor: DEFAULT_CUSTOM_COLOR,
  };
}

/** Per-user key so two accounts on one browser do not share a palette. */
export function userAppearanceStorageKey(userId: number): string {
  return `${THEME_STORAGE_KEY}:user:${userId}`;
}

function appearanceStorageKey(userId?: number | null): string {
  return typeof userId === "number"
    ? userAppearanceStorageKey(userId)
    : THEME_STORAGE_KEY;
}

/** Persist both fields. A user id writes that account's key, not the shared boot key. */
export function writeStoredAppearance(
  appearance: StoredAppearance,
  userId?: number | null,
): void {
  localStorage.setItem(
    appearanceStorageKey(userId),
    JSON.stringify({
      preference: appearance.preference,
      palette: appearance.palette,
      customColor:
        normalizeHexColor(appearance.customColor ?? "") ?? DEFAULT_CUSTOM_COLOR,
    }),
  );
  if (typeof userId !== "number") {
    localStorage.removeItem(LEGACY_PALETTE_STORAGE_KEY);
  }
}

/** One-shot boot read + migrate for ThemeProvider initial state. */
export function loadAppearanceOnBoot(): StoredAppearance {
  const appearance = readStoredAppearance();
  writeStoredAppearance(appearance);
  return appearance;
}
