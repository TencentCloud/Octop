import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import styles from "../index.module.less";

/**
 * Collapsed-by-default block for expert create/edit drawers.
 * Children stay mounted while hidden so a save without expanding still
 * submits defaults (model, backend, trajectory, …).
 */
export default function MoreConfigCollapse({
  children,
}: {
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <div className={styles.moreConfig}>
      <button
        type="button"
        className={styles.moreConfigToggle}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className={styles.moreConfigLabel}>
          {t("experts.moreConfig")}
          <ChevronDown
            size={14}
            aria-hidden
            className={open ? styles.moreConfigIconOpen : styles.moreConfigIcon}
          />
        </span>
      </button>
      <div style={open ? undefined : { display: "none" }}>{children}</div>
    </div>
  );
}
