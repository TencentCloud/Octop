import { useState } from "react";
import { useTranslation } from "react-i18next";
import peek from "./assets/octop-mascot-peek.webp";
import typeMascot from "./assets/octop-mascot-type.webp";
import styles from "./LoadingPage.module.less";

const MASCOT_IMAGES = [peek, typeMascot];

function nextMascot(current: string): string {
  const others = MASCOT_IMAGES.filter((src) => src !== current);
  return others[Math.floor(Math.random() * others.length)] ?? current;
}

interface LoadingPageProps {
  status: string;
  stuck: boolean;
}

export default function LoadingPage({ status, stuck }: LoadingPageProps) {
  const { t } = useTranslation();
  const [mascot, setMascot] = useState(() => nextMascot(""));

  return (
    <div
      className={`${styles.loading} ${stuck ? styles.error : ""}`}
      data-testid="loading-panel"
      data-stuck={stuck ? "1" : "0"}
    >
      <div className={styles.card} data-testid="loading-card">
        <img
          className={styles.mascot}
          src={mascot}
          alt="Octop"
          draggable={false}
          data-testid="mascot"
          onClick={() => setMascot((current) => nextMascot(current))}
        />
        <p className={styles.brand} data-testid="loading-brand">
          Octop
        </p>
        <p className={styles.hint}>{t("desktopShell.loadingHint")}</p>
        <div className={styles.footer} data-testid="loading-footer">
          <div
            className={styles.bar}
            role="progressbar"
            aria-hidden="true"
            data-testid="loading-bar"
          >
            <span className={styles.barFill} />
          </div>
          <p className={styles.status} data-testid="status">
            {status}
          </p>
        </div>
      </div>
    </div>
  );
}
