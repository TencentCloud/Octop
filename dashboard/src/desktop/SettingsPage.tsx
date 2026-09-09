import { useTranslation } from "react-i18next";
import type { DesktopSettings } from "./wails";
import styles from "./SettingsPage.module.less";

interface SettingsPageProps {
  value: DesktopSettings;
  error: string;
  onChange: (next: DesktopSettings) => void;
  onShowMain: () => void;
  onQuit: () => void;
}

export default function SettingsPage({
  value,
  error,
  onChange,
  onShowMain,
  onQuit,
}: SettingsPageProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.wrap} data-testid="settings-panel">
      <h1 className={styles.title}>{t("desktopShell.settingsTitle")}</h1>
      <p className={styles.subtitle}>{t("desktopShell.settingsSubtitle")}</p>
      <div className={styles.card}>
        <div className={styles.row}>
          <div>
            <div className={styles.label}>{t("desktopShell.lang")}</div>
            <small className={styles.hint}>{t("desktopShell.langHint")}</small>
          </div>
          <select
            className={styles.select}
            aria-label={t("desktopShell.lang")}
            value={value.locale === "zh" ? "zh" : "en"}
            onChange={(event) =>
              onChange({ ...value, locale: event.target.value })
            }
          >
            <option value="zh">中文</option>
            <option value="en">English</option>
          </select>
        </div>
        <div className={styles.row}>
          <div>
            <div className={styles.label}>{t("desktopShell.autostart")}</div>
            <small className={styles.hint}>
              {t("desktopShell.autostartHint")}
            </small>
          </div>
          <label className={styles.switch}>
            <input
              type="checkbox"
              checked={value.autostart}
              onChange={(event) =>
                onChange({ ...value, autostart: event.target.checked })
              }
            />
            <span />
          </label>
        </div>
        <div className={styles.row}>
          <div>
            <div className={styles.label}>{t("desktopShell.tray")}</div>
            <small className={styles.hint}>{t("desktopShell.trayHint")}</small>
          </div>
          <label className={styles.switch}>
            <input
              type="checkbox"
              checked={value.minimizeToTray}
              onChange={(event) =>
                onChange({ ...value, minimizeToTray: event.target.checked })
              }
            />
            <span />
          </label>
        </div>
        <div className={styles.row}>
          <div>
            <div className={styles.label}>{t("desktopShell.sleep")}</div>
            <small className={styles.hint}>{t("desktopShell.sleepHint")}</small>
          </div>
          <label className={styles.switch}>
            <input
              type="checkbox"
              checked={value.preventSleep}
              onChange={(event) =>
                onChange({ ...value, preventSleep: event.target.checked })
              }
            />
            <span />
          </label>
        </div>
      </div>
      <div className={styles.actions}>
        <button className={styles.primary} type="button" onClick={onShowMain}>
          {t("desktopShell.showMain")}
        </button>
        <button className={styles.ghost} type="button" onClick={onQuit}>
          {t("desktopShell.quit")}
        </button>
      </div>
      <p
        className={
          error ? styles.error : `${styles.error} ${styles.errorHidden}`
        }
        data-testid="settings-status"
      >
        {error}
      </p>
    </div>
  );
}
