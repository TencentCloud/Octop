import { Share2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SharedResourceBadge } from "../../../components/SharedResourceBadge";
import styles from "../index.module.less";

/**
 * Shared-session mark.
 *
 * The owner gets the same pill as a shared expert. Someone opening a session
 * shared with them gets the same icon used in the session list.
 */
export default function SessionShareMark({
  contributed,
  owned,
}: {
  contributed?: boolean;
  owned?: boolean;
}) {
  const { t } = useTranslation();
  if (!contributed) return null;
  if (owned === false) {
    const label = t("chat.sharedSession");
    return (
      <span
        className={styles.sessionRowPinIndicator}
        title={label}
        aria-label={label}
      >
        <Share2 size={12} strokeWidth={2} aria-hidden />
      </span>
    );
  }
  return <SharedResourceBadge shared owned />;
}
