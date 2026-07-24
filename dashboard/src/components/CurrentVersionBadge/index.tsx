import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Tooltip } from "antd";
import { useUpdateStatus } from "../../hooks/useUpdateStatus";
import { useUserRole } from "../../hooks/useUserRole";
import styles from "./index.module.less";

interface CurrentVersionBadgeProps {
  isMobile?: boolean;
}

export default function CurrentVersionBadge({
  isMobile,
}: CurrentVersionBadgeProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const role = useUserRole();
  const { status } = useUpdateStatus();

  const version = status?.current_version;
  if (!version) return null;

  const isAdmin = role === "admin";
  const tooltip = isAdmin
    ? t("header.currentVersionAdmin", { version })
    : t("header.currentVersion", { version });
  const label = `v${version}`;

  if (isAdmin) {
    return (
      <Tooltip title={tooltip} mouseEnterDelay={0.35}>
        <button
          type="button"
          className={`${styles.versionBadge} ${
            isMobile ? styles.versionBadgeMobile : ""
          } ${styles.versionBadgeClickable}`}
          onClick={() => navigate("/admin/advanced?tab=updates")}
          aria-label={tooltip}
        >
          {label}
        </button>
      </Tooltip>
    );
  }

  return (
    <Tooltip title={tooltip} mouseEnterDelay={0.35}>
      <span
        className={`${styles.versionBadge} ${
          isMobile ? styles.versionBadgeMobile : ""
        }`}
        aria-label={tooltip}
      >
        {label}
      </span>
    </Tooltip>
  );
}
