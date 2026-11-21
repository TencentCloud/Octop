import { useTranslation } from "react-i18next";
import { Tooltip } from "antd";
import cx from "classnames";
import styles from "./index.module.less";

interface BetaBadgeProps {
  isMobile?: boolean;
  /** Replaces the product-version tooltip when the badge marks one feature. */
  tooltip?: string;
}

export default function BetaBadge({ isMobile, tooltip }: BetaBadgeProps) {
  const { t } = useTranslation();
  const tip = tooltip ?? t("header.betaTooltip");

  return (
    <Tooltip title={tip} mouseEnterDelay={0.35}>
      <span
        className={cx(styles.betaBadge, isMobile && styles.betaBadgeMobile)}
        aria-label={tip}
      >
        {t("header.betaBadge")}
      </span>
    </Tooltip>
  );
}
