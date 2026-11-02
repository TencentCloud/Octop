/**
 * AddProviderCard — dashed "+" card that opens the custom-provider drawer.
 */
import { Card } from "antd";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "../../index.module.less";

interface AddProviderCardProps {
  onClick: () => void;
  isHover: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  label?: string;
}

export function AddProviderCard({
  onClick,
  isHover,
  onMouseEnter,
  onMouseLeave,
  label,
}: AddProviderCardProps) {
  const { t } = useTranslation();
  return (
    <Card
      hoverable
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={
        isHover
          ? `${styles.providerCard} ${styles.hover} ${styles.addProviderCard}`
          : `${styles.providerCard} ${styles.normal} ${styles.addProviderCard}`
      }
    >
      <div className={styles.addProviderCardInner}>
        <Plus size={28} strokeWidth={1.75} className={styles.addProviderIcon} />
        <span className={styles.addProviderLabel}>
          {label ?? t("models.addEmbeddingProvider")}
        </span>
      </div>
    </Card>
  );
}
