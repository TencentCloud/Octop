import { useTranslation } from "react-i18next";
import { Tooltip } from "antd";
import cx from "classnames";
import styles from "./index.module.less";

interface BetaBadgeProps {
  isMobile?: boolean;
}

export default function BetaBadge({ isMobile }: BetaBadgeProps) {
  const { t } = useTranslation();

  return (
    <Tooltip title={t("header.betaTooltip")} mouseEnterDelay={0.35}>
      <span
        className={cx(styles.betaBadge, isMobile && styles.betaBadgeMobile)}
        aria-label={t("header.betaTooltip")}
      >
        {t("header.betaBadge")}
      </span>
    </Tooltip>
  );
}
