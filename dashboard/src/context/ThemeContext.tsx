import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import {
  DEFAULT_PALETTE,
  PALETTE_STORAGE_KEY,
  VALID_PALETTES,
  type ThemePalette,
} from "../styles/themePalettes";

export type ThemePreference = "system" | "light" | "dark";

export type ThemeMode = "light" | "dark";

export type { ThemePalette };

interface ThemeContextValue {
  /** The resolved mode applied to the UI */
  mode: ThemeMode;
  /** The user's preference (may be "system") */
  preference: ThemePreference;
  /** Set preference */
  setPreference: (p: ThemePreference) => void;
  /** Brand color palette (orthogonal to light/dark) */
  palette: ThemePalette;
  /** Set brand palette */
  setPalette: (p: ThemePalette) => void;
  /** Legacy toggle kept for backward compat (cycles light/dark) */
  toggle: () => void;
  /** Whether the current mode is considered "dark" for Ant Design */
  isDark: boolean;
}

const ThemeContext = createContext<ThemeContextValue>({
  mode: "light",
  preference: "system",
  setPreference: () => {},
  palette: DEFAULT_PALETTE,
  setPalette: () => {},
  toggle: () => {},
  isDark: false,
});

function resolveMode(pref: ThemePreference): ThemeMode {
  if (pref === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return pref;
}

export function isDarkMode(mode: ThemeMode): boolean {
  return mode === "dark";
}

const VALID_PREFERENCES: ThemePreference[] = ["system", "light", "dark"];

function readStoredPalette(): ThemePalette {
  const stored = localStorage.getItem(PALETTE_STORAGE_KEY);
  if (stored && (VALID_PALETTES as string[]).includes(stored)) {
    return stored as ThemePalette;
  }
  return DEFAULT_PALETTE;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => {
    const stored = localStorage.getItem("theme") as ThemePreference | null;
    if (stored && VALID_PREFERENCES.includes(stored)) return stored;
    return "system";
  });

  const [palette, setPaletteState] = useState<ThemePalette>(() => {
    const stored = readStoredPalette();
    document.documentElement.setAttribute("data-palette", stored);
    return stored;
  });

  const [mode, setMode] = useState<ThemeMode>(() => resolveMode(preference));

  // Listen for system color scheme changes when preference is "system"
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (preference === "system") {
        setMode(mq.matches ? "dark" : "light");
      }
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [preference]);

  // Apply resolved mode
  useEffect(() => {
    setMode(resolveMode(preference));
  }, [preference]);

  useEffect(() => {
    localStorage.setItem("theme", preference);
    document.documentElement.setAttribute("data-theme", mode);

    // Keep the PWA theme-color meta tag in sync with the resolved mode so
    // the browser chrome (address bar, status bar, PWA title bar) matches.
    const themeColor = mode === "dark" ? "#1a1c28" : "#ffffff";
    document
      .querySelectorAll<HTMLMetaElement>("meta[name='theme-color']")
      .forEach((el) => {
        el.content = themeColor;
      });
  }, [mode, preference]);

  useEffect(() => {
    localStorage.setItem(PALETTE_STORAGE_KEY, palette);
    document.documentElement.setAttribute("data-palette", palette);
  }, [palette]);

  const setPreference = useCallback((p: ThemePreference) => {
    setPreferenceState(p);
  }, []);

  const setPalette = useCallback((p: ThemePalette) => {
    setPaletteState(p);
  }, []);

  const toggle = useCallback(() => {
    setPreferenceState((prev) => {
      if (prev === "light") return "dark";
      if (prev === "dark") return "light";
      return mode === "light" ? "dark" : "light";
    });
  }, [mode]);

  return (
    <ThemeContext.Provider
      value={{
        mode,
        preference,
        setPreference,
        palette,
        setPalette,
        toggle,
        isDark: isDarkMode(mode),
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
