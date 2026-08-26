import { memo } from "react";
import { Switch } from "antd";
import { useTranslation } from "react-i18next";

import type {
  ConnectorCatalogEntry,
  ConnectorInstance,
} from "../../../api/modules/connectors";
import { ConnectorLogo, connectorAccent } from "./connectorDefs";
import styles from "./index.module.less";

interface ConnectorCardProps {
  entry: ConnectorCatalogEntry;
  instance: ConnectorInstance | null;
  onConfigure: (
    entry: ConnectorCatalogEntry,
    instance: ConnectorInstance | null,
  ) => void;
  onToggleEnabled: (instance: ConnectorInstance, enabled: boolean) => void;
}

export const ConnectorCard = memo(function ConnectorCard({
  entry,
  instance,
  onConfigure,
  onToggleEnabled,
}: ConnectorCardProps) {
  const { t } = useTranslation();
  const accent = connectorAccent(entry);
  const disabled = entry.phase !== "available";
  const configured = instance != null && instance.has_credentials;
  const enabled = configured && instance?.status === "active";

  return (
    <div
      className={`${styles.typeCard}${
        disabled ? ` ${styles.typeCardDisabled}` : ""
      }`}
      style={{ "--connector-accent": accent } as React.CSSProperties}
      onClick={() => !disabled && onConfigure(entry, instance)}
      role="button"
      tabIndex={disabled ? -1 : 0}
      onKeyDown={(e) =>
        e.key === "Enter" && !disabled && onConfigure(entry, instance)
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
            {configured
              ? t("connectors.clickToManage", "点击管理连接")
              : t("connectors.clickToConnect", "点击连接")}
          </div>
          {configured && instance && (
            <div
              className={styles.typeCardSwitch}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
            >
              <Switch
                size="small"
                checked={enabled}
                onChange={(checked) => onToggleEnabled(instance, checked)}
              />
            </div>
          )}
        </div>
      ) : (
        <div className={styles.typeCardFooterSpacer} aria-hidden />
      )}
    </div>
  );
});
