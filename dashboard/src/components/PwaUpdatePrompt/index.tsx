import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { applyUpdate, hasPendingAppUpdate } from "../../pwa";
import { updateApi } from "../../api/modules/update";
import { useCurrentUser } from "../../hooks/useCurrentUser";
import { userCan } from "../../utils/permissions";
import styles from "./index.module.less";

/**
 * Dismissal flag for the current tab. The waiting Service Worker survives a
 * reload, so without this the banner pops again on every navigation. Scoped to
 * the session so a genuinely new version can prompt next time the tab opens.
 */
export const PWA_UPDATE_DISMISSED_KEY = "pwa:update-dismissed";

/**
 * Listens for the "pwa:update-ready" event (dispatched by sw-register.ts) and
 * renders a dismissible banner so the user can choose when to reload.
 * Mount once above the router so the login page sees it too. If the event
 * fired before this component mounted, the waiting worker is checked directly.
 *
 * The banner is shown on every page, including login. Reloading picks up the
 * new frontend.
 * Restarting the backend service still requires the ``update`` permission.
 *
 * When the process is running as a system service (OCTOP_SERVICE_MODE is
 * set) and the user may update, clicking the action also restarts the backend
 * so the new Python package takes effect alongside the new frontend bundle.
 */
export default function PwaUpdatePrompt() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const [visible, setVisible] = useState(false);
  const [serviceMode, setServiceMode] = useState<string | null>(null);

  const canUpdate = userCan(user, "update");

  useEffect(() => {
    let cancelled = false;
    const show = () => {
      try {
        if (sessionStorage.getItem(PWA_UPDATE_DISMISSED_KEY)) return;
      } catch {
        // private mode / storage disabled — still allow the prompt
      }
      if (!cancelled) setVisible(true);
    };
    window.addEventListener("pwa:update-ready", show);
    void hasPendingAppUpdate().then((pending) => {
      if (pending) show();
    });
    return () => {
      cancelled = true;
      window.removeEventListener("pwa:update-ready", show);
    };
  }, []);

  // Fetch service mode once so we know whether to also restart the backend.
  useEffect(() => {
    if (!canUpdate) return;
    updateApi
      .getUpdateStatus()
      .then((s) => setServiceMode(s.service_mode))
      .catch(() => {});
  }, [canUpdate]);

  if (!visible) return null;

  const handleUpdate = async () => {
    setVisible(false);
    // Frontend reload is enough for everyone. Only an operator may restart
    // the backend service that is serving this page.
    if (canUpdate && serviceMode) {
      updateApi.restartService().catch(() => {});
    }
    await applyUpdate();
  };

  const handleDismiss = () => {
    try {
      sessionStorage.setItem(PWA_UPDATE_DISMISSED_KEY, "1");
    } catch {
      // ignore
    }
    setVisible(false);
  };

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
