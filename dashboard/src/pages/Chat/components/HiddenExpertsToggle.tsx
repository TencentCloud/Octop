import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import cx from "classnames";
import styles from "../index.module.less";

/** Centered disclosure for the hidden-expert group in the chat nav. */
export default function HiddenExpertsToggle({
  expanded,
  count,
  onToggle,
}: {
  expanded: boolean;
  count: number;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      className={styles.hiddenExpertsToggle}
      aria-expanded={expanded}
      onClick={onToggle}
    >
      <span className={styles.hiddenExpertsToggleSide} aria-hidden />
      <span className={styles.hiddenExpertsToggleLabel}>
        {expanded
          ? t("chat.expertListHiddenCollapse")
          : t("chat.expertListHidden", { count })}
      </span>
      <span className={styles.hiddenExpertsToggleSide}>
        <ChevronDown
          size={14}
          strokeWidth={2}
          aria-hidden
          className={cx(
            styles.hiddenExpertsToggleChevron,
            expanded && styles.hiddenExpertsToggleChevronOpen,
          )}
        />
      </span>
    </button>
  );
}
