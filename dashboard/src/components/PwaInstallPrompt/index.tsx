import { useEffect, useSyncExternalStore, useState } from "react";
import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { Download, MonitorDown, Share, X } from "lucide-react";
import { AppDialog } from "../AppDialog";
import {
  subscribePwaPrompt,
  getPwaInstallSnapshot,
  triggerInstall,
  waitForInstallPrompt,
} from "../../pwa-prompt";
import { isDesktopShell } from "../../utils/desktopChrome";
import styles from "./index.module.less";

const DISMISSED_KEY = "pwa:install-dismissed";
const IOS_SHOWN_KEY = "pwa:ios-guide-shown";

/** Any iOS browser — all support "Add to Home Screen" via the share sheet. */
function isIosDevice(): boolean {
  const ua = navigator.userAgent;
  const ipadOs =
    navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  return /iphone|ipad|ipod/i.test(ua) || ipadOs;
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    ("standalone" in window.navigator &&
      (window.navigator as { standalone?: boolean }).standalone === true)
  );
}

// ─── iOS guide sheet ──────────────────────────────────────────────────────────

export function IosGuide({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <AppDialog
      open
      onClose={onClose}
      ariaLabel={t("pwaInstall.iosTitle")}
      className={styles.iosOverlay}
    >
      <div className={styles.iosSheet}>
        <button
          className={styles.guideClose}
          onClick={onClose}
          aria-label={t("common.close")}
        >
          <X size={18} />
        </button>
        <div className={styles.guideTitle}>{t("pwaInstall.iosTitle")}</div>
        <p className={styles.guideDesc}>{t("pwaInstall.iosDesc")}</p>
        <ol className={styles.guideList}>
          <li>
            <span className={styles.guideStep}>1</span>
            <span>
              {t("pwaInstall.iosStep1Prefix")}{" "}
              <Share size={14} className={styles.guideInlineIcon} aria-hidden />{" "}
              {t("pwaInstall.iosStep1Suffix")}
            </span>
          </li>
          <li>
            <span className={styles.guideStep}>2</span>
            <span>{t("pwaInstall.iosStep2")}</span>
          </li>
          <li>
            <span className={styles.guideStep}>3</span>
            <span>{t("pwaInstall.iosStep3")}</span>
          </li>
        </ol>
        <div className={styles.iosArrow}>↓</div>
      </div>
    </AppDialog>
  );
}

// ─── Desktop / Android guide (when beforeinstallprompt is not yet available) ──

export function DesktopInstallGuide({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const isEdge = /edg/i.test(navigator.userAgent);
  return (
    <AppDialog
      open
      onClose={onClose}
      ariaLabel={t("pwaInstall.desktopTitle")}
      className={styles.desktopOverlay}
    >
      <div className={styles.desktopSheet}>
        <button
          className={styles.guideClose}
          onClick={onClose}
          aria-label={t("common.close")}
        >
          <X size={18} />
        </button>
        <div className={styles.guideTitle}>{t("pwaInstall.desktopTitle")}</div>
        <p className={styles.guideDesc}>{t("pwaInstall.desktopDesc")}</p>
        <ol className={styles.guideList}>
          <li>
            <span className={styles.guideStep}>1</span>
            <span>
              {t("pwaInstall.desktopStep1Prefix")}{" "}
              <MonitorDown
                size={14}
                className={styles.guideInlineIcon}
                aria-hidden
              />{" "}
              {t("pwaInstall.desktopStep1Suffix")}
            </span>
          </li>
          <li>
            <span className={styles.guideStep}>2</span>
            <span>
              {t("pwaInstall.desktopStep2Prefix")}
              {isEdge
                ? t("pwaInstall.browserEdge")
                : t("pwaInstall.browserInstall")}
              {t("pwaInstall.desktopStep2Suffix")}
            </span>
          </li>
          <li>
            <span className={styles.guideStep}>3</span>
            <span>{t("pwaInstall.desktopStep3")}</span>
          </li>
        </ol>
        <p className={styles.guideHint}>{t("pwaInstall.desktopHint")}</p>
      </div>
    </AppDialog>
  );
}

interface PwaInstallPromptProps {
  compact?: boolean;
  /**
   * `chatFloat` matches the chat page right-side circular float buttons
   * (browser / expert / files).
   */
  appearance?: "default" | "chatFloat";
}

/**
 * Android/Desktop: reads the deferred prompt captured at module load time
 * (pwa-prompt.ts) via useSyncExternalStore, so it correctly reflects the event
 * even when it fires before React mounts.
 *
 * iOS: shows an install button that opens the step-by-step guide sheet.
 */
export default function PwaInstallPrompt({
  compact,
  appearance = "default",
}: PwaInstallPromptProps) {
  const installState = useSyncExternalStore(
    subscribePwaPrompt,
    getPwaInstallSnapshot,
  );
  const [showIosGuide, setShowIosGuide] = useState(false);
  const [showDesktopGuide, setShowDesktopGuide] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [ios] = useState(() => isIosDevice());
  const [dismissed, setDismissed] = useState(
    () => !!localStorage.getItem(DISMISSED_KEY),
  );

  if (isStandalone() || isDesktopShell() || installState.installed) return null;

  // Chat right float: always expose the install entry until the app is
  // installed (ignore Header dismiss + beforeinstallprompt lag). Dev has no
  // SW, so the old swReady gate hid the button entirely on localhost Vite.
  // Header compact still requires readiness (or iOS) and honors dismiss.
  const chatFloat = appearance === "chatFloat";
  const browserInstallReady =
    ios || installState.prompt || installState.swReady;
  if (!chatFloat && (dismissed || !browserInstallReady)) return null;

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, "1");
    setDismissed(true);
    setShowIosGuide(false);
    setShowDesktopGuide(false);
  };

  const handleAndroidInstall = async () => {
    if (ios) {
      setShowIosGuide(true);
      return;
    }
    if (installing) return;
    setInstalling(true);
    try {
      if (!installState.prompt) {
        await waitForInstallPrompt(4000);
      }
      const outcome = await triggerInstall();
      if (outcome === "accepted") return;
      if (outcome === "dismissed") {
        localStorage.setItem(DISMISSED_KEY, "1");
        setDismissed(true);
        return;
      }
      setShowDesktopGuide(true);
    } finally {
      setInstalling(false);
    }
  };

  const tooltipTitle = ios
    ? "添加到主屏幕"
    : installState.prompt
    ? "安装为桌面应用"
    : "安装为桌面应用";

  const btnClass = chatFloat
    ? styles.installBtnChatFloat
    : `${styles.installBtn} ${compact ? styles.installBtnCompact : ""}`;

  const button = (
    <button
      type="button"
      className={btnClass}
      onClick={() => void handleAndroidInstall()}
      disabled={installing}
      aria-label="安装应用"
    >
      <Download
        aria-hidden
        size={chatFloat ? 20 : compact ? 15 : 16}
        strokeWidth={chatFloat ? 2.1 : 1.8}
        className={styles.installIcon}
      />
      {!compact && !chatFloat && <span className={styles.label}>安装</span>}
    </button>
  );

  return (
    <>
      <Tooltip title={tooltipTitle} placement={chatFloat ? "left" : "top"}>
        {chatFloat ? (
          <span className={styles.chatFloatBtnWrap}>{button}</span>
        ) : (
          button
        )}
      </Tooltip>

      {ios && showIosGuide && <IosGuide onClose={handleDismiss} />}
      {!ios && showDesktopGuide && (
        <DesktopInstallGuide onClose={() => setShowDesktopGuide(false)} />
      )}
    </>
  );
}

// ─── Auto-prompt for iOS (mounted in MainLayout) ──────────────────────────────

/**
 * On iOS, automatically shows the guide sheet after a short delay on
 * the first visit. Covers Chat mobile where the global Header is hidden.
 */
export function PwaAutoPrompt() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!isIosDevice() || isStandalone() || isDesktopShell()) return;
    if (
      localStorage.getItem(DISMISSED_KEY) ||
      localStorage.getItem(IOS_SHOWN_KEY)
    )
      return;
    const t = setTimeout(() => setShow(true), 4000);
    return () => clearTimeout(t);
  }, []);

  const handleClose = () => {
    localStorage.setItem(IOS_SHOWN_KEY, "1");
    setShow(false);
  };

  if (!show) return null;
  return <IosGuide onClose={handleClose} />;
}
