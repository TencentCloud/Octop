import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Switch } from "antd";
import { RefreshCw, Sparkles } from "lucide-react";
import { modal } from "../../../utils/antdModal";
import {
  getDesktopBridge,
  type DesktopClientSettings,
  type DesktopUpdateCheckResult,
} from "../../../utils/desktopBridge";
import { useUpdateStatus } from "../../../hooks/useUpdateStatus";
import { TabPanelHeader } from "./TabPanelHeader";
import styles from "./UpdateConfig.module.less";

/**
 * Desktop-shell update panel. The shell detects/downloads/installs the whole
 * release (shell + Dashboard + Python runtime); this panel only reads the shell
 * channel preference. Detection only lights the shared update icon; this page
 * is where the version and confirm dialog appear. It never calls the Python
 * self-update API.
 */
export default function DesktopUpdatePanel() {
  const { t } = useTranslation();
  const { status, refreshStatus } = useUpdateStatus();
  const [settings, setSettings] = useState<DesktopClientSettings | null>(null);
  const [checking, setChecking] = useState(false);
  const result: DesktopUpdateCheckResult | null = status
    ? {
        status: status.error
          ? "error"
          : status.has_update
          ? "update-available"
          : "up-to-date",
        currentVersion: status.current_version,
        latestVersion: status.latest_version,
        error: status.error,
      }
    : null;

  useEffect(() => {
    void getDesktopBridge()
      ?.clientSettings.get()
      .then(setSettings)
      .catch(() => {});
  }, []);

  const handleStableOnlyChange = useCallback(
    async (checked: boolean) => {
      const next = await getDesktopBridge()?.clientSettings.set({
        stableOnly: checked,
      });
      if (next) setSettings(next);
      await refreshStatus(true);
    },
    [refreshStatus],
  );

  const handleCheck = useCallback(async () => {
    setChecking(true);
    try {
      await refreshStatus(true);
    } finally {
      setChecking(false);
    }
  }, [refreshStatus]);

  const handleUpgrade = useCallback(() => {
    const latest = result?.latestVersion;
    if (!latest) return;
    // Close immediately. Download progress stays on the taskbar; failures stay
    // on the shell's system dialog. Awaiting installUpdate would pin this modal
    // open for the whole download.
    modal.confirm({
      title: t("advancedSettings.update.shellConfirmTitle", {
        version: latest,
      }),
      content: t("advancedSettings.update.shellConfirmBody", {
        current: result?.currentVersion || "—",
      }),
      okText: t("advancedSettings.update.upgradeButton"),
      cancelText: t("advancedSettings.update.later"),
      onOk: () => {
        void getDesktopBridge()
          ?.installUpdate()
          ?.catch(() => {});
      },
    });
  }, [result, t]);

  const hasUpdate = result?.status === "update-available";

  return (
    <div className={styles.container}>
      <TabPanelHeader
        icon={<RefreshCw size={22} />}
        title={t("advancedSettings.update.title")}
        description={t("advancedSettings.update.shellManaged")}
      />

      <section
        className={`${styles.panel} ${styles.panelConstrained}`}
        aria-label={t("advancedSettings.update.panelTitle")}
      >
        <div className={styles.panelTitleRow}>
          <span className={styles.panelTitleIcon}>
            <Sparkles size={16} />
          </span>
          <h3 className={styles.panelTitle}>
            {t("advancedSettings.update.panelTitle")}
          </h3>
        </div>

        <div className={styles.stableOnlyRow}>
          <Switch
            checked={settings?.stableOnly !== false}
            onChange={(checked) => void handleStableOnlyChange(checked)}
            disabled={checking}
          />
          <div className={styles.stableOnlyCopy}>
            <p className={styles.stableOnlyLabel}>
              {t("advancedSettings.update.stableOnlyLabel")}
            </p>
            <p className={styles.stableOnlyHint}>
              {t("advancedSettings.update.stableOnlyHint")}
            </p>
          </div>
        </div>

        <div className={styles.versionGrid}>
          <div className={styles.versionCard}>
            <span className={styles.versionLabel}>
              {t("advancedSettings.update.currentVersion")}
            </span>
            <span className={styles.versionValue}>
              {result?.currentVersion || "—"}
            </span>
          </div>
          <div className={styles.versionCard}>
            <span className={styles.versionLabel}>
              {t("advancedSettings.update.latestVersion")}
            </span>
            <span className={styles.versionValue}>
              {result?.latestVersion ?? (
                <span className={styles.notChecked}>
                  {t("advancedSettings.update.notChecked")}
                </span>
              )}
            </span>
            <div className={styles.versionBadges}>
              {hasUpdate && (
                <span className={styles.badge}>
                  {t("advancedSettings.update.updateAvailable")}
                </span>
              )}
            </div>
          </div>
        </div>

        {result?.status === "error" && (
          <div className={`${styles.alert} ${styles.alertError}`}>
            <span>{result.error}</span>
          </div>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.btnSecondary}
            onClick={() => void handleCheck()}
            disabled={checking}
          >
            <RefreshCw
              size={14}
              className={checking ? styles.spinning : undefined}
            />
            {checking
              ? t("advancedSettings.update.checking")
              : t("advancedSettings.update.checkButton")}
          </button>

          {hasUpdate && (
            <button
              type="button"
              className={styles.btnPrimary}
              onClick={handleUpgrade}
            >
              {t("advancedSettings.update.upgradeButton")}
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
