import { Typography } from "antd";
import { useTranslation } from "react-i18next";

import styles from "./AssetsTab.module.less";

const { Text } = Typography;

/**
 * Activity tab — a **placeholder**, on purpose (PLAN §4.1 / Q21).
 *
 * The feed (posted notes, mentions, member activity) belongs to the next batch.
 * This component exists so the tab renders an honest "not yet" instead of an
 * empty box, and it is deliberately inert: no hook, no fetch, no subscription.
 * That is asserted by a test which fails if any request is issued — otherwise
 * this file would be the place where the next batch's scope leaks in.
 */
function DynamicTab() {
  const { t } = useTranslation();

  return (
    <div className={styles.section} data-testid="project-dynamic">
      <div className={styles.placeholder}>
        <Text strong>{t("projects.dynamicPlaceholder")}</Text>
        <Text className={styles.placeholderHint}>
          {t("projects.dynamicComingSoon")}
        </Text>
      </div>
    </div>
  );
}

export default DynamicTab;
