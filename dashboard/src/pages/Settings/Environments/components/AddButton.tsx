import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import styles from "../index.module.less";

interface AddButtonProps {
  onClick: () => void;
  className?: string;
}

export function AddButton({ onClick, className }: AddButtonProps) {
  const { t } = useTranslation();

  return (
    <div className={cx(styles.addBar, className)}>
      <button
        className={styles.addBtn}
        onClick={onClick}
        title={t("environments.addVariable")}
      >
        <Plus size={16} />
        <span>{t("environments.addVariable")}</span>
      </button>
    </div>
  );
}
