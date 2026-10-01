import { useTranslation } from "react-i18next";
import { Tooltip } from "antd";
import { iconForName } from "../../Experts/components/iconForName";
import styles from "../index.module.less";

interface RemoteExpertHintProps {
  agent?: {
    bridge?: boolean | null;
    bridge_connection_name?: string | null;
    bridge_connection_icon?: string | null;
  } | null;
  /** Force show without checking ``agent.bridge`` (title bar). */
  show?: boolean;
  connectionName?: string | null;
  connectionIcon?: string | null;
  /** Hide the connection name (chips / tight pickers). */
  compact?: boolean;
}

/** Marks a sidebar / picker / experts row as a remote Bridge shadow expert. */
export default function RemoteExpertHint({
  agent,
  show,
  connectionName,
  connectionIcon,
  compact,
}: RemoteExpertHintProps) {
  const { t } = useTranslation();
  const visible = show ?? Boolean(agent?.bridge);
  if (!visible) return null;
  const name =
    (connectionName ?? agent?.bridge_connection_name ?? "").trim() || "";
  const icon =
    (connectionIcon ?? agent?.bridge_connection_icon ?? "").trim() || "cloudy";
  const tip = name
    ? t("chat.remoteExpert.banner", { name })
    : t("chat.remoteExpert.flag");
  const label = compact ? null : name || null;
  return (
    <Tooltip title={tip} mouseEnterDelay={0.35}>
      <span
        className={`${styles.remoteExpertFlag}${
          compact ? ` ${styles.remoteExpertFlagCompact}` : ""
        }`}
        aria-label={tip}
        onClick={(event) => event.stopPropagation()}
      >
        <span className={styles.remoteExpertIcon} aria-hidden>
          {iconForName(icon, 11)}
        </span>
        {label ? (
          <span className={styles.remoteExpertName}>{label}</span>
        ) : null}
      </span>
    </Tooltip>
  );
}
