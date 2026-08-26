import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { applyUpdate } from "../../pwa";
import { updateApi } from "../../api/modules/update";
import styles from "./index.module.less";

/**
 * Listens for the "pwa:update-ready" event (dispatched by sw-register.ts) and
 * renders a dismissible banner so the user can choose when to reload.
 * Designed to be mounted once in MainLayout.
 *
 * When the process is running as a system service (OCTOP_SERVICE_MODE is
 * set), clicking the update-now action also triggers a backend service restart so that
 * the new Python package takes effect alongside the new frontend bundle.
 */
export default function PwaUpdatePrompt() {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  const [serviceMode, setServiceMode] = useState<string | null>(null);

  useEffect(() => {
    const handler = () => setVisible(true);
    window.addEventListener("pwa:update-ready", handler);
    return () => window.removeEventListener("pwa:update-ready", handler);
  }, []);

  // Fetch service mode once so we know whether to also restart the backend.
  useEffect(() => {
    updateApi
      .getUpdateStatus()
      .then((s) => setServiceMode(s.service_mode))
      .catch(() => {});
  }, []);

  if (!visible) return null;

  const handleUpdate = async () => {
    setVisible(false);
    // If running as a system service, trigger backend restart first.
    // applyUpdate() reloads once after posting SKIP_WAITING.
    if (serviceMode) {
      updateApi.restartService().catch(() => {});
    }
    await applyUpdate();
  };

  const handleDismiss = () => setVisible(false);

  return (
    <div className={styles.banner} role="alert" aria-live="polite">
      <span className={styles.icon}>✨</span>
      <span className={styles.text}>{t("pwa.updateReady")}</span>
      <button className={styles.btnPrimary} onClick={handleUpdate}>
        {t("pwa.updateNow")}
      </button>
      <button
        className={styles.btnGhost}
        onClick={handleDismiss}
        aria-label={t("pwa.later")}
      >
        ✕
      </button>
    </div>
  );
}
