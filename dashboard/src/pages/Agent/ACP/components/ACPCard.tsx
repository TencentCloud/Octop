import { Switch, Tooltip } from "antd";
import { CheckCircle, Plug } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ACPRunnerConfig } from "../../../../api/types/acp";
import { runnerIcon, runnerIntroKey, runnerLabelKey } from "../constants";
import styles from "../../Channels/index.module.less";

interface ACPCardProps {
  runnerKey: string;
  config: ACPRunnerConfig;
  isHover: boolean;
  toggleLoading?: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onToggleEnabled: (runnerKey: string, checked: boolean) => void;
}

function isConfigured(config: ACPRunnerConfig): boolean {
  return Boolean(config.command?.trim());
}

export function ACPCard({
  runnerKey,
  config,
  isHover,
  toggleLoading,
  onClick,
  onMouseEnter,
  onMouseLeave,
  onToggleEnabled,
}: ACPCardProps) {
  const { t } = useTranslation();
  const labelKey = runnerLabelKey(runnerKey);
  const label = labelKey ? t(labelKey) : runnerKey;
  const introKey = runnerIntroKey(runnerKey);
  const intro = introKey
    ? t(introKey)
    : t("acp.intro_custom", {
        command: config.command || t("acp.notSet"),
      });
  const configured = isConfigured(config);
  const icon = runnerIcon(runnerKey);

  const cardClass = [
    styles.channelCard,
    config.enabled ? styles.enabled : styles.normal,
    isHover ? styles.hover : "",
  ]
    .filter(Boolean)
    .join(" ");

  const renderStatusBadge = () => {
    if (config.enabled) {
      return (
        <span className={`${styles.statusBadge} ${styles.statusConnected}`}>
          <CheckCircle size={14} />
          {configured ? t("common.enabled") : t("acp.runnerNeedsConfig")}
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

  return (
    <div
      className={cardClass}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className={styles.cardTop}>
        <img src={icon} alt={label} className={styles.channelIcon} />
        <span className={styles.cardTitle}>{label}</span>
        <div onClick={(e) => e.stopPropagation()}>
          <Tooltip
            title={
              !configured && !config.enabled
                ? t("acp.clickCardToConfigure")
                : undefined
            }
          >
            <Switch
              size="small"
              checked={config.enabled}
              loading={toggleLoading}
              disabled={!configured && !config.enabled}
              onChange={(checked) => onToggleEnabled(runnerKey, checked)}
            />
          </Tooltip>
        </div>
      </div>

      <p className={styles.cardDescription}>{intro}</p>

      <div className={styles.cardBottom}>{renderStatusBadge()}</div>
    </div>
  );
}
