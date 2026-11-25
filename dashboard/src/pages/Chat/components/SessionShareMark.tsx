import { Share2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

/**
 * Shared-session mark — same compact Share icon for owners and viewers.
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
  const label =
    owned === false
      ? t("chat.sharedSession")
      : t("sharedResource.shared", "已共享");
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
