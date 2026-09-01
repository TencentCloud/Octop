import type { DesktopChromeStyle } from "../../utils/desktopChrome";
import { emitDesktopWindowAction } from "../../utils/desktopChrome";
import { Minus, Square, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "./DesktopWindowControls.module.less";

interface DesktopWindowControlsProps {
  chrome: DesktopChromeStyle;
}

export default function DesktopWindowControls({
  chrome,
}: DesktopWindowControlsProps) {
  const { t } = useTranslation();
  const minimise = t("desktopChrome.minimize", "Minimize");
  const maximise = t("desktopChrome.maximize", "Maximize");
  const close = t("desktopChrome.close", "Close");

  if (chrome === "mac") {
    return (
      <div
        className={styles.mac}
        data-octop-no-drag="true"
        aria-label={t("desktopChrome.group", "Window controls")}
      >
        <button
          type="button"
          className={`${styles.light} ${styles.zoom}`}
          aria-label={maximise}
          onClick={() => emitDesktopWindowAction("toggle-maximise")}
        >
          <span className={styles.glyph} aria-hidden>
            +
          </span>
        </button>
        <button
          type="button"
          className={`${styles.light} ${styles.min}`}
          aria-label={minimise}
          onClick={() => emitDesktopWindowAction("minimise")}
        >
          <span className={styles.glyph} aria-hidden>
            –
          </span>
        </button>
        <button
          type="button"
          className={`${styles.light} ${styles.close}`}
          aria-label={close}
          onClick={() => emitDesktopWindowAction("close")}
        >
          <span className={styles.glyph} aria-hidden>
            ×
          </span>
        </button>
      </div>
    );
  }

  return (
    <div
      className={styles.windows}
      data-octop-no-drag="true"
      aria-label={t("desktopChrome.group", "Window controls")}
    >
      <button
        type="button"
        className={styles.winBtn}
        aria-label={minimise}
        onClick={() => emitDesktopWindowAction("minimise")}
      >
        <Minus size={12} strokeWidth={2} aria-hidden />
      </button>
      <button
        type="button"
        className={styles.winBtn}
        aria-label={maximise}
        onClick={() => emitDesktopWindowAction("toggle-maximise")}
      >
        <Square size={10} strokeWidth={2} aria-hidden />
      </button>
      <button
        type="button"
        className={`${styles.winBtn} ${styles.winClose}`}
        aria-label={close}
        onClick={() => emitDesktopWindowAction("close")}
      >
        <X size={12} strokeWidth={2} aria-hidden />
      </button>
    </div>
  );
}
