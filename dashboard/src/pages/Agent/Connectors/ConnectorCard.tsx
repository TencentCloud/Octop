import { memo } from "react";
import { useTranslation } from "react-i18next";

import type { ConnectorCatalogEntry } from "../../../api/modules/connectors";
import { ConnectorLogo, connectorAccent } from "./connectorDefs";
import styles from "./index.module.less";

interface ConnectorCardProps {
  entry: ConnectorCatalogEntry;
  onConfigure: (entry: ConnectorCatalogEntry, instance: null) => void;
}

export const ConnectorCard = memo(function ConnectorCard({
  entry,
  onConfigure,
}: ConnectorCardProps) {
  const { t } = useTranslation();
  const accent = connectorAccent(entry);
  const disabled = entry.phase !== "available";

  return (
    <div
      className={`${styles.typeCard}${
        disabled ? ` ${styles.typeCardDisabled}` : ""
      }`}
      style={{ "--connector-accent": accent } as React.CSSProperties}
      onClick={() => !disabled && onConfigure(entry, null)}
      role="button"
      tabIndex={disabled ? -1 : 0}
      onKeyDown={(e) =>
        e.key === "Enter" && !disabled && onConfigure(entry, null)
      }
    >
      <div className={styles.typeCardBody}>
        <div className={styles.typeCardHeader}>
          <div className={styles.typeCardIconLarge}>
            <ConnectorLogo kind={entry.kind} icon={entry.icon} size={40} />
          </div>
          <div className={styles.typeCardTitle}>{entry.name}</div>
        </div>

        <div className={styles.typeCardDesc}>{entry.description}</div>
      </div>

      {!disabled ? (
        <div className={styles.typeCardFooter}>
          <div className={styles.typeCardHint}>
            {t("connectors.clickToConnect", "点击连接")}
          </div>
        </div>
      ) : (
        <div className={styles.typeCardFooterSpacer} aria-hidden />
      )}
    </div>
  );
});
