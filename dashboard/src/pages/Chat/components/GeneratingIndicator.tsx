import { useTranslation } from "react-i18next";
import { useElapsedSince } from "../../../hooks/useElapsedSeconds";
import styles from "../index.module.less";

interface GeneratingIndicatorProps {
  /** When set, appends elapsed seconds (useful while waiting for the first token). */
  startedAt?: number | null;
  showElapsed?: boolean;
  /**
   * Host turn already settled; only team members (or late peers) are still
   * producing — softer named copy.
   */
  membersOnly?: boolean;
  /** Named speakers still generating (e.g. ["临床助手"]). */
  speakerNames?: ReadonlyArray<string>;
}

/**
 * Bottom-left live status for the turn. Stop/cancel stays on the composer —
 * this row is status text only so it can remain visible the whole time.
 */
export default function GeneratingIndicator({
  startedAt = null,
  showElapsed = false,
  membersOnly = false,
  speakerNames = [],
}: GeneratingIndicatorProps) {
  const { t } = useTranslation();
  const elapsedAnchor =
    startedAt != null && startedAt > 0 ? startedAt : Date.now();
  const elapsed = useElapsedSince(elapsedAnchor);
  const showTimer = Boolean(
    !membersOnly && showElapsed && startedAt != null && startedAt > 0,
  );

  const named = speakerNames.filter((n) => n.trim());
  let label: string;
  if (membersOnly || named.length > 0) {
    if (named.length === 1) {
      label = t("chat.memberResponding", {
        name: named[0],
        defaultValue: "{{name}} 正在回答",
      });
    } else if (named.length > 1) {
      label = t("chat.membersRespondingNamed", {
        names: named.join(t("chat.nameJoin", { defaultValue: "、" })),
        defaultValue: "{{names}} 正在回答",
      });
    } else {
      label = t("chat.membersResponding", {
        defaultValue: "成员回答中",
      });
    }
  } else if (showTimer) {
    label = t("chat.generatingWithElapsed", {
      seconds: elapsed,
      defaultValue: "生成中 · {{seconds}}s",
    });
  } else {
    label = t("chat.generating", "生成中");
  }

  return (
    <div className={styles.turnInset}>
      <div
        className={styles.generatingIndicator}
        role="status"
        aria-live="polite"
      >
        <span className={styles.thinkingDot} />
        <span className={styles.thinkingDot} />
        <span className={styles.thinkingDot} />
        <span className={styles.generatingText}>{label}</span>
      </div>
    </div>
  );
}
