import { useEffect, useState } from "react";
import DesktopWindowControls from "../components/DesktopWindowControls";
import {
  applyDesktopChrome,
  DESKTOP_DRAG_REGION_CLASS,
  resolveDesktopChromeStyle,
  WINDOW_CONTROLS_INSET,
} from "../utils/desktopChrome";
import { normalizeUiLocale, type UiLocale } from "../utils/localePrefs";
import i18n, { applyDesktopLocale } from "./i18n";
import LoadingPage from "./LoadingPage";
import SettingsPage from "./SettingsPage";
import chrome from "./chrome.module.less";
import {
  callApp,
  isStuckStatus,
  onDesktopStatus,
  type DesktopSettings,
} from "./wails";

const SETTINGS_INSET = "36px";

function isSettingsMode(): boolean {
  return new URLSearchParams(window.location.search).get("settings") === "1";
}

function asSettings(raw: DesktopSettings): DesktopSettings {
  return {
    locale: normalizeUiLocale(raw.locale),
    autostart: !!raw.autostart,
    minimizeToTray: raw.minimizeToTray !== false,
    preventSleep: !!raw.preventSleep,
    port: raw.port,
  };
}

export default function ShellApp() {
  const settingsMode = isSettingsMode();
  const chromeStyle = resolveDesktopChromeStyle();
  const [status, setStatus] = useState(() =>
    i18n.t("desktopShell.statusWait", "Starting, please wait…"),
  );
  const [settings, setSettings] = useState<DesktopSettings | null>(null);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    applyDesktopChrome(chromeStyle);
    if (settingsMode) {
      document.documentElement.dataset.mode = "settings";
      document.documentElement.style.setProperty(
        "--window-controls-inset-end",
        SETTINGS_INSET,
      );
    } else {
      document.documentElement.style.setProperty(
        "--window-controls-inset-end",
        `${WINDOW_CONTROLS_INSET[chromeStyle]}px`,
      );
    }
  }, [chromeStyle, settingsMode]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const loaded = asSettings(
          await callApp<DesktopSettings>("GetSettingsStatus"),
        );
        if (cancelled) return;
        setSettings(loaded);
        await applyDesktopLocale(loaded.locale as UiLocale);
        if (!cancelled) {
          setStatus(
            i18n.t("desktopShell.statusWait", "Starting, please wait…"),
          );
        }
      } catch {
        if (!cancelled) setSettings(asSettings({} as DesktopSettings));
      }
      if (cancelled) return;
      await onDesktopStatus((text) => {
        if (!cancelled) setStatus(text);
      });
      if (!settingsMode) {
        try {
          await callApp("BootReady");
        } catch {
          // browser preview without Wails
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [settingsMode]);

  const persist = async (next: DesktopSettings) => {
    const previous = settings;
    setSettings(next);
    try {
      const saved = asSettings(
        await callApp<DesktopSettings>("SaveSettings", next),
      );
      setSettings(saved);
      setSaveError("");
      await applyDesktopLocale(saved.locale as UiLocale);
    } catch (error) {
      if (previous) setSettings(previous);
      setSaveError(String(error));
    }
  };

  return (
    <>
      <div
        className={`${chrome.bar} ${DESKTOP_DRAG_REGION_CLASS}`}
        data-testid="window-chrome"
      />
      <DesktopWindowControls
        chrome={chromeStyle}
        closeOnly={settingsMode}
        onClose={settingsMode ? () => void callApp("HideSettings") : undefined}
      />
      {settingsMode ? (
        settings ? (
          <SettingsPage
            value={settings}
            error={saveError}
            onChange={(next) => void persist(next)}
            onShowMain={() => void callApp("ShowMain")}
            onQuit={() => void callApp("Quit")}
          />
        ) : null
      ) : (
        <LoadingPage status={status} stuck={isStuckStatus(status)} />
      )}
    </>
  );
}
