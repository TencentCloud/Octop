import { memo } from "react";
import { Typography } from "antd";
import { useTranslation } from "react-i18next";

import type { ConnectorCatalogEntry } from "../../../api/modules/connectors";
import { ConnectorLogo, connectorAccent } from "./connectorDefs";
import styles from "./index.module.less";
import { WORKBUDDY_UI } from "../../../workbuddy/variant";
import ConnectorTile from "../../../workbuddy/ConnectorTile";

interface ConnectorCardProps {
  entry: ConnectorCatalogEntry;
  onConfigure: (entry: ConnectorCatalogEntry, instance: null) => void;
  onOpen?: (entry: ConnectorCatalogEntry) => void;
}

export const ConnectorCard = memo(function ConnectorCard({
  entry,
  onConfigure,
  onOpen,
}: ConnectorCardProps) {
  const { t } = useTranslation();
  const accent = connectorAccent(entry);
  const disabled = entry.phase !== "available";

  if (WORKBUDDY_UI)
    return (
      <ConnectorTile
        name={entry.name}
        description={entry.description}
        icon={<ConnectorLogo kind={entry.kind} icon={entry.icon} size={28} />}
        disabled={disabled}
        status={
          disabled ? (
            <span className="connector-card-badge">
              {t("workbuddy.notConnected")}
            </span>
          ) : undefined
        }
        onOpen={() => (onOpen ? onOpen(entry) : onConfigure(entry, null))}
        actions={
          <button
            type="button"
            className="connector-connect-btn"
            disabled={disabled}
            onClick={() => onConfigure(entry, null)}
            aria-label={t("connectors.clickToConnect", "点击连接")}
            title={t("connectors.clickToConnect", "点击连接")}
          >
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path
                d="M8.6 8.6V13H7.4V8.6H3V7.4H7.4V3H8.6V7.4H13V8.6H8.6Z"
                fill="currentColor"
                fillRule="evenodd"
              />
            </svg>
          </button>
        }
      />
    );

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
          <div className={styles.typeCardTitleCol}>
            <Typography.Text
              className={styles.typeCardTitle}
              ellipsis={{ tooltip: entry.name }}
            >
              {entry.name}
            </Typography.Text>
            <span
              className={styles.categoryChip}
              style={{ color: accent, background: `${accent}18` }}
            >
              {t(`connectors.category.${entry.category}`, entry.category)}
            </span>
          </div>
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
