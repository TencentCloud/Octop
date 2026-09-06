/**
 * StorageTypeCard — preset storage backend type card in the supported-types tab.
 */
import { memo } from "react";
import { CheckCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CatalogTypeCard } from "../../../components/CatalogTypeCard";
import { storageKindGroup, type StorageTypeDef } from "./useStorageBackends";
import cardStyles from "../../../components/CatalogTypeCard/catalogTypeCard.module.less";
import styles from "./storage.module.less";

interface StorageTypeCardProps {
  typeDef: StorageTypeDef;
  isConfigured: boolean;
  onClick: (typeDef: StorageTypeDef) => void;
}

export const StorageTypeCard = memo(function StorageTypeCard({
  typeDef,
  isConfigured,
  onClick,
}: StorageTypeCardProps) {
  const { t } = useTranslation();
  const group = storageKindGroup(typeDef.kind);

  return (
    <CatalogTypeCard
      accent={typeDef.color}
      title={t(typeDef.nameKey)}
      description={t(typeDef.descKey)}
      hint={t("storage.clickToConfigure")}
      icon={typeDef.icon}
      tag={
        group ? (
          <span
            className={styles.groupChip}
            style={{
              color: typeDef.color,
              background: `${typeDef.color}18`,
            }}
          >
            {t(group.titleKey)}
          </span>
        ) : undefined
      }
      onClick={() => onClick(typeDef)}
      configuredBadge={
        isConfigured ? (
          <div className={cardStyles.configuredBadge}>
            <CheckCircle size={15} />
            <span>{t("storage.configuredBadge")}</span>
          </div>
        ) : undefined
      }
    />
  );
});
