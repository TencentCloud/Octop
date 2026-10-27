import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, Switch } from "antd";
import { KeyRound, RefreshCw, Sparkles } from "lucide-react";
import { message } from "@/utils/antdMessage";
import { getAuthToken } from "../../../api/request";
import {
  getDesktopBridge,
  type DesktopClientSettings,
  type DesktopUpdateCheckResult,
} from "../../../utils/desktopBridge";
import { TabPanelHeader } from "./TabPanelHeader";
import styles from "./UpdateConfig.module.less";

const { confirm } = Modal;

/**
 * Desktop-shell update panel. The shell detects/downloads/installs the whole
 * release (shell + Dashboard + Python runtime); this panel only reads the shell
 * channel preference, triggers a shell check, and opens the shell confirmation.
 * It never calls the Python self-update API.
 */
export default function DesktopUpdatePanel() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<DesktopClientSettings | null>(null);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<DesktopUpdateCheckResult | null>(null);

  useEffect(() => {
    void getDesktopBridge()
      ?.clientSettings.get()
      .then(setSettings)
      .catch(() => {});
  }, []);

  const handleStableOnlyChange = useCallback(async (checked: boolean) => {
    const next = await getDesktopBridge()?.clientSettings.set({ stableOnly: checked });
    if (next) setSettings(next);
  }, []);

  const handleCheck = useCallback(async () => {
    setChecking(true);
    try {
      const res = await getDesktopBridge()?.checkForUpdates();
      if (res) setResult(res);
    } catch {
      setResult({
        status: "error",
        currentVersion: "",
        latestVersion: null,
        error: t("advancedSettings.update.networkError"),
      });
    } finally {
      setChecking(false);
    }
  }, [t]);

  const handleUpgrade = useCallback(() => {
    // The shell owns the confirm → download → install hand-off; nothing here can
    // fail in a way this panel should surface (the shell shows its own dialogs).
    void getDesktopBridge()?.openUpdateConfirmation().catch(() => {});
  }, []);

  const handleResetLogin = useCallback(() => {
    const session = getDesktopBridge()?.session;
    if (!session) return;
    confirm({
      title: t("advancedSettings.update.deviceLoginConfirmTitle"),
      content: t("advancedSettings.update.deviceLoginConfirmBody"),
      okText: t("advancedSettings.update.deviceLoginButton"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          // Only renewal stops: the JWT in hand keeps working until it expires,
          // which is why the copy says "after this session ends".
          const ok = await session.revoke(getAuthToken());
          if (ok) message.success(t("advancedSettings.update.deviceLoginSuccess"));
          else message.error(t("advancedSettings.update.deviceLoginFailed"));
        } catch {
          message.error(t("advancedSettings.update.deviceLoginFailed"));
        }
      },
    });
  }, [t]);

  const hasUpdate = result?.status === "update-available";

  return (
    <div className={styles.container}>
      <TabPanelHeader
        icon={<RefreshCw size={22} />}
        title={t("advancedSettings.update.title")}
        description={t("advancedSettings.update.shellManaged")}
      />

      <div className={styles.layout}>
        <section className={styles.panel} aria-label={t("advancedSettings.update.panelTitle")}>
          <div className={styles.panelTitleRow}>
            <span className={styles.panelTitleIcon}>
              <Sparkles size={16} />
            </span>
            <h3 className={styles.panelTitle}>{t("advancedSettings.update.panelTitle")}</h3>
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
              <RefreshCw size={14} className={checking ? styles.spinning : undefined} />
              {checking
                ? t("advancedSettings.update.checking")
                : t("advancedSettings.update.checkButton")}
            </button>

            {hasUpdate && (
              <button type="button" className={styles.btnPrimary} onClick={handleUpgrade}>
                {t("advancedSettings.update.upgradeButton")}
              </button>
            )}
          </div>
        </section>

        {getDesktopBridge()?.session ? (
          <section
            className={styles.panel}
            aria-label={t("advancedSettings.update.deviceLoginTitle")}
          >
            <div className={styles.panelTitleRow}>
              <span className={styles.panelTitleIcon}>
                <KeyRound size={16} />
              </span>
              <h3 className={styles.panelTitle}>
                {t("advancedSettings.update.deviceLoginTitle")}
              </h3>
            </div>
            <p className={styles.panelDesc}>{t("advancedSettings.update.deviceLoginHint")}</p>

            <div className={styles.actions}>
              <button
                type="button"
                className={styles.btnDanger}
                onClick={handleResetLogin}
              >
                <KeyRound size={14} />
                {t("advancedSettings.update.deviceLoginButton")}
              </button>
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
