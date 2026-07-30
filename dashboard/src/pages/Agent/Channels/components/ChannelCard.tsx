import { Switch, Tooltip } from "antd";
import { CheckCircle, Loader2, Plug } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  CHANNEL_LABEL_KEYS,
  CHANNEL_LABELS,
  CHANNEL_ICONS,
  type ChannelKey,
} from "./constants";
import type { ChannelRow } from "../useChannels";
import styles from "../index.module.less";

interface ChannelCardProps {
  channelKey: ChannelKey;
  /** True if the agent has an enabled channel row for this kind. */
  enabled: boolean;
  /** True if the agent has any channel row for this kind (enabled or not). */
  hasChannel: boolean;
  isHover: boolean;
  enableLoading?: boolean;
  testLoading?: boolean;
  testResult?: { ok: boolean; error?: string } | null;
  runtime?: ChannelRow["runtime"];
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onToggleEnabled: (channelKey: ChannelKey, checked: boolean) => void;
}

export function ChannelCard({
  channelKey,
  enabled,
  hasChannel,
  isHover,
  enableLoading,
  testLoading,
  testResult,
  runtime,
  onClick,
  onMouseEnter,
  onMouseLeave,
  onToggleEnabled,
}: ChannelCardProps) {
  const { t } = useTranslation();
  const icon = CHANNEL_ICONS[channelKey];
  const labelKey = CHANNEL_LABEL_KEYS[channelKey];
  const label = labelKey
    ? t(labelKey)
    : CHANNEL_LABELS[channelKey] ?? channelKey;

  const renderStatusBadge = () => {
    if (testLoading) {
      return (
        <span className={`${styles.statusBadge} ${styles.statusChecking}`}>
          <Loader2 size={14} />
          {t("channels.checking")}
        </span>
      );
    }
    if (testResult) {
      if (testResult.ok) {
        return (
          <span className={`${styles.statusBadge} ${styles.statusConnected}`}>
            <CheckCircle size={14} />
            {t("channels.connected")}
          </span>
        );
      }
      return (
        <Tooltip title={testResult.error ?? t("common.unknownError")}>
          <span
            className={`${styles.statusBadge} ${styles.statusDisconnected}`}
          >
            <Plug size={14} />
            {t("channels.disconnected")}
          </span>
        </Tooltip>
      );
    }
    if (enabled && runtime && !runtime.connected) {
      return (
        <Tooltip title={runtime.error ?? t("channels.unknownReason")}>
          <span
            className={`${styles.statusBadge} ${styles.statusDisconnected}`}
          >
            <Plug size={14} />
            {t("channels.disconnected")}
          </span>
        </Tooltip>
      );
    }
    if (enabled && runtime?.connected) {
      return (
        <span className={`${styles.statusBadge} ${styles.statusConnected}`}>
          <CheckCircle size={14} />
          {t("channels.connected")}
        </span>
      );
    }
    if (enabled) {
      return (
        <span className={`${styles.statusBadge} ${styles.statusConnected}`}>
          <CheckCircle size={14} />
          {t("channels.channelEnabled")}
        </span>
      );
    }
    return (
      <span className={`${styles.statusBadge} ${styles.statusInactive}`}>
        <Plug size={14} />
        {t("common.disabled")}
      </span>
    );
  };

  const cardClass = [
    styles.channelCard,
    enabled ? styles.enabled : styles.normal,
    isHover ? styles.hover : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={cardClass}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className={styles.cardTop}>
        {icon ? (
          <img src={icon} alt={label} className={styles.channelIcon} />
        ) : (
          <div className={styles.channelIcon} />
        )}
        <span className={styles.cardTitle}>{label}</span>
        <div onClick={(e) => e.stopPropagation()}>
          <Tooltip
            title={!hasChannel ? t("channels.clickCardToEdit") : undefined}
          >
            <Switch
              size="small"
              checked={enabled}
              loading={enableLoading}
              disabled={!hasChannel && !enabled}
              onChange={(checked) => onToggleEnabled(channelKey, checked)}
            />
          </Tooltip>
        </div>
      </div>

      <p className={styles.cardDescription}>
        {t(`channels.intro_${channelKey}`, label)}
      </p>

      <div className={styles.cardBottom}>{renderStatusBadge()}</div>
    </div>
  );
}
