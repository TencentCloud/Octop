import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

interface ScrollToBottomButtonProps {
  visible: boolean;
  onClick: () => void;
}

export default function ScrollToBottomButton({
  visible,
  onClick,
}: ScrollToBottomButtonProps) {
  const { t } = useTranslation();
  const label = t("chat.scrollToBottom");
  return (
    <button
      className={`${styles.scrollToBottomBtn} ${
        visible
          ? styles.scrollToBottomBtnVisible
          : styles.scrollToBottomBtnHidden
      }`}
      onClick={onClick}
      type="button"
      title={label}
      aria-label={label}
      aria-hidden={!visible}
      tabIndex={visible ? 0 : -1}
    >
      <ChevronDown size={16} strokeWidth={2.5} aria-hidden />
      <span>{label}</span>
    </button>
  );
}
