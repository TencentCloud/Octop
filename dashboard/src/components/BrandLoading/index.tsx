import { useTranslation } from "react-i18next";

import { useTheme } from "../../context/ThemeContext";
import { publicUrl } from "../../utils/publicUrl";
import OctopSpinner from "../OctopSpinner";
import styles from "./BrandLoading.module.less";

interface BrandLoadingProps {
  /** Status line beside the arc. Defaults to the shared loading label. */
  label?: string;
  /** Cover the viewport. Route fallbacks fill their parent instead. */
  viewport?: boolean;
}

/**
 * Full-page wait: the horizontal lockup above the shared arc and a status
 * line. Same composition as the shell splash and the first-paint boot
 * screen in index.html.
 */
export default function BrandLoading({ label, viewport }: BrandLoadingProps) {
  const { t } = useTranslation();
  const { mode } = useTheme();
  const logoSrc =
    mode === "dark"
      ? publicUrl("logo_horizontal_white.png")
      : publicUrl("logo_horizontal_dark.png");

  return (
    <div
      className={viewport ? `${styles.host} ${styles.viewport}` : styles.host}
      role="status"
      aria-live="polite"
    >
      <div className={styles.stack}>
        <img
          className={styles.logo}
          src={logoSrc}
          alt="Octop"
          height={72}
        />
        <p className={styles.status}>
          <OctopSpinner />
          <span>{label ?? t("common.loading")}</span>
        </p>
      </div>
    </div>
  );
}
