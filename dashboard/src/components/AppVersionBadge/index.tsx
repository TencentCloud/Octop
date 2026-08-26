import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Tooltip } from "antd";
import { ArrowUpCircle } from "lucide-react";
import { useUpdateStatus } from "../../hooks/useUpdateStatus";
import { useCurrentUser } from "../../hooks/useCurrentUser";
import { userCan } from "../../utils/permissions";
import styles from "./index.module.less";

interface AppVersionBadgeProps {
  isMobile?: boolean;
}

export default function AppVersionBadge({ isMobile }: AppVersionBadgeProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useCurrentUser();
  const { status, hasUpdate } = useUpdateStatus();

  const canUpdate = userCan(user, "update");
  if (!status?.current_version || !hasUpdate || !canUpdate) return null;

  const tooltip = t("header.versionUpdateAvailable", {
    current: status.current_version,
    latest: status.latest_version,
    defaultValue: `当前 v${status.current_version}，新版本 v${status.latest_version} 可用，点击前往更新`,
  });

  const handleClick = () => {
    navigate("/admin/advanced?tab=updates");
  };

  return (
    <Tooltip title={tooltip} mouseEnterDelay={0.35}>
      <button
        type="button"
        className={`${styles.headerVersion} ${
          isMobile ? styles.headerVersionMobile : ""
        } ${styles.headerVersionClickable}`}
        onClick={handleClick}
        aria-label={tooltip}
      >
        <ArrowUpCircle size={isMobile ? 14 : 15} strokeWidth={2} />
      </button>
    </Tooltip>
  );
}
