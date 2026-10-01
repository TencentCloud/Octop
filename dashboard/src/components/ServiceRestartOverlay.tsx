import { useEffect } from "react";
import type { CSSProperties } from "react";
import { CheckCircle, AlertTriangle, Power } from "lucide-react";
import { Button, Spin } from "antd";
import { useTranslation } from "react-i18next";
import type { RestartPhase } from "../hooks/useServiceRestart";
import { AppDialog } from "./AppDialog";
import styles from "./ServiceRestartOverlay.module.less";

const OVERLAY_Z_INDEX = 2_147_483_000;

const OVERLAY_BLOCK_STYLE: CSSProperties = {
  position: "fixed",
  top: 0,
  left: 0,
  width: "100%",
  height: "100dvh",
  zIndex: OVERLAY_Z_INDEX,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(0, 0, 0, 0.62)",
  backdropFilter: "blur(6px)",
  WebkitBackdropFilter: "blur(6px)",
  pointerEvents: "auto",
};

const PANEL_STYLE: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 12,
  maxWidth: 420,
  width: "min(420px, calc(100vw - 48px))",
  padding: "32px 28px",
  borderRadius: 12,
  background: "var(--fn-bg-primary, #fff)",
  border: "1px solid var(--fn-border-primary, rgba(0,0,0,0.08))",
  boxShadow: "0 12px 40px rgba(0, 0, 0, 0.25)",
  textAlign: "center",
};

const TITLE_STYLE: CSSProperties = {
  margin: 0,
  fontSize: 16,
  fontWeight: 600,
  color: "var(--fn-text-primary, #111)",
};

const SUBTITLE_STYLE: CSSProperties = {
  margin: 0,
  fontSize: 13,
  color: "var(--fn-text-secondary, #666)",
  lineHeight: 1.5,
};

interface ServiceRestartOverlayProps {
  phase: RestartPhase;
  onConfirm?: () => void;
  onCancel?: () => void;
  onDismiss?: () => void;
  onRetry?: () => void;
}

export default function ServiceRestartOverlay({
  phase,
  onConfirm,
  onCancel,
  onDismiss,
  onRetry,
}: ServiceRestartOverlayProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (phase === "idle") return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [phase]);

  if (phase === "idle") return null;

  return (
    <AppDialog
      open
      role="alertdialog"
      dismissable={false}
      onClose={onDismiss ?? (() => {})}
      ariaLabel={t("advancedSettings.update.restarting")}
      style={OVERLAY_BLOCK_STYLE}
    >
      <div
        className={styles.panel}
        style={PANEL_STYLE}
        aria-busy={phase === "restarting"}
      >
        {phase === "confirm" && (
          <>
            <Power size={28} className={styles.confirmIcon} aria-hidden />
            <p style={TITLE_STYLE}>
              {t("advancedSettings.update.restartConfirmTitle")}
            </p>
            <p style={SUBTITLE_STYLE}>
              {t("advancedSettings.update.restartConfirmContent")}
            </p>
            <div className={styles.actions}>
              {onCancel && (
                <Button onClick={onCancel}>
                  {t("advancedSettings.update.restartCancel")}
                </Button>
              )}
              {onConfirm && (
                <Button type="primary" onClick={onConfirm}>
                  {t("advancedSettings.update.restartServiceBtn")}
                </Button>
              )}
            </div>
          </>
        )}
        {phase === "restarting" && (
          <>
            <Spin
              size="large"
              tip={t("advancedSettings.update.restartingHint")}
            />
            <p style={TITLE_STYLE}>{t("advancedSettings.update.restarting")}</p>
          </>
        )}
        {phase === "success" && (
          <>
            <CheckCircle size={28} className={styles.successIcon} aria-hidden />
            <p style={TITLE_STYLE}>
              {t("advancedSettings.update.restartSuccess")}
            </p>
            <p style={SUBTITLE_STYLE}>
              {t("advancedSettings.update.restartReadyHint")}
            </p>
          </>
        )}
        {phase === "timeout" && (
          <>
            <AlertTriangle size={28} className={styles.warnIcon} aria-hidden />
            <p style={TITLE_STYLE}>
              {t("advancedSettings.update.restartTimeout")}
            </p>
            <div className={styles.actions}>
              {onRetry && (
                <Button type="primary" onClick={onRetry}>
                  {t("advancedSettings.update.restartServiceBtn")}
                </Button>
              )}
              {onDismiss && (
                <Button onClick={onDismiss}>{t("common.close")}</Button>
              )}
            </div>
          </>
        )}
      </div>
    </AppDialog>
  );
}
