import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  isMacPlatform,
  railShortcutAria,
  railShortcutLabel,
} from "../utils/railShortcuts";
import edgeStyles from "./RailEdgeControl.module.less";
import styles from "./SplitSeamHandle.module.less";

interface SplitSeamHandleProps {
  onCollapseNav: () => void;
  onExpandHistory: () => void;
}

/**
 * One control on the nav's trailing edge while the history rail is folded.
 *
 * The left half folds the nav. The right half reopens the conversation list.
 * It replaces the pair of small pills that used to share this line.
 */
export default function SplitSeamHandle({
  onCollapseNav,
  onExpandHistory,
}: SplitSeamHandleProps) {
  const { t } = useTranslation();
  const mac = isMacPlatform();
  const collapseLabel = t("layout.collapseNav", "收起导航栏");
  const expandLabel = t("chat.expandHistorySidebar", "展开对话历史");

  return (
    <div className={`${edgeStyles.edge} ${edgeStyles.edgeEnd}`}>
      <div className={edgeStyles.line} aria-hidden />
      <div className={styles.split} data-testid="history-split-handle">
        <button
          type="button"
          className={styles.half}
          onClick={onCollapseNav}
          aria-label={collapseLabel}
          title={`${collapseLabel} (${railShortcutLabel("toggle-nav", mac)})`}
          aria-keyshortcuts={railShortcutAria("toggle-nav")}
        >
          <ChevronLeft size={12} strokeWidth={2} aria-hidden />
        </button>
        <button
          type="button"
          className={styles.half}
          onClick={onExpandHistory}
          aria-label={expandLabel}
          title={`${expandLabel} (${railShortcutLabel("toggle-history", mac)})`}
          aria-keyshortcuts={railShortcutAria("toggle-history")}
        >
          <ChevronRight size={12} strokeWidth={2} aria-hidden />
        </button>
      </div>
    </div>
  );
}
