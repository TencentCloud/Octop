import { Switch, Tooltip } from "antd";
import { CheckCircle, Plug } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import type { ACPRunnerConfig } from "../../../../api/types/acp";
import {
  isBuiltinRunner,
  runnerIcon,
  runnerIntroKey,
  runnerLabelKey,
} from "../constants";
import styles from "../../Channels/index.module.less";
import acpStyles from "../index.module.less";

interface ACPCardProps {
  runnerKey: string;
  config: ACPRunnerConfig;
  isHover: boolean;
  toggleLoading?: boolean;
  /** When true (e.g. current agent directory sandbox), runner enable is locked. */
  interactionDisabled?: boolean;
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
  interactionDisabled = false,
  onClick,
  onMouseEnter,
  onMouseLeave,
  onToggleEnabled,
}: ACPCardProps) {
  const { t } = useTranslation();
  const label = isBuiltinRunner(runnerKey)
    ? t(runnerLabelKey(runnerKey))
    : runnerKey;
  const intro = isBuiltinRunner(runnerKey)
    ? t(runnerIntroKey(runnerKey))
    : t("acp.intro_custom", {
        command: config.command || t("acp.notSet"),
      });
  const configured = isConfigured(config);
  const icon = runnerIcon(runnerKey);
  // Under sandbox, block turning runners on; still allow turning them off
  // so account-global config is not stuck while viewing a jailed agent.
  const switchDisabled =
    (interactionDisabled && !config.enabled) ||
    (!configured && !config.enabled);

  const cardClass = cx(
    styles.channelCard,
    config.enabled ? styles.enabled : styles.normal,
    isHover && !interactionDisabled && styles.hover,
    interactionDisabled && acpStyles.runnerCardDisabled,
  );

  const renderStatusBadge = () => {
    if (interactionDisabled && !config.enabled) {
      return (
        <span className={cx(styles.statusBadge, styles.statusInactive)}>
          <Plug size={14} />
          {t("acp.runnerUnavailable")}
        </span>
      );
    }
    if (config.enabled) {
      return (
        <span className={cx(styles.statusBadge, styles.statusConnected)}>
          <CheckCircle size={14} />
          {configured ? t("common.enabled") : t("acp.runnerNeedsConfig")}
        </span>
      );
    }
    return (
      <span className={cx(styles.statusBadge, styles.statusInactive)}>
        <Plug size={14} />
        {t("common.disabled")}
      </span>
    );
  };

  return (
    <div
      className={cardClass}
      onClick={interactionDisabled ? undefined : onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className={styles.cardTop}>
        <img
          src={icon}
          alt={label}
          className={cx(
            styles.channelIcon,
            runnerKey === "pi" && acpStyles.invertOnDark,
          )}
        />
        <span className={styles.cardTitle}>{label}</span>
        <div onClick={(e) => e.stopPropagation()}>
          <Tooltip
            title={
              interactionDisabled && !config.enabled
                ? t("acp.outboundBlockedTooltip")
                : !configured && !config.enabled
                ? t("acp.clickCardToConfigure")
                : undefined
            }
          >
            <Switch
              size="small"
              checked={config.enabled}
              loading={toggleLoading}
              disabled={switchDisabled}
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
