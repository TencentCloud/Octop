import type { ReactNode } from "react";
import { Collapse } from "antd";
import styles from "./index.module.less";

interface SsoProviderCardProps {
  kind: string;
  title: string;
  description: string;
  extra?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

export default function SsoProviderCard({
  kind,
  title,
  description,
  extra,
  defaultOpen = false,
  children,
}: SsoProviderCardProps) {
  return (
    <Collapse
      className={styles.ssoCollapse}
      defaultActiveKey={defaultOpen ? ["provider"] : []}
      items={[
        {
          key: "provider",
          label: (
            <div className={styles.ssoCollapseLabel}>
              <div className={styles.ssoCollapseLabelTop}>
                <span className={styles.ssoKindBadge}>{kind}</span>
                <span className={styles.ssoProviderTitle}>{title}</span>
              </div>
              <span className={styles.ssoProviderDesc}>{description}</span>
            </div>
          ),
          extra: extra ? (
            <div
              className={styles.ssoCollapseExtra}
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => event.stopPropagation()}
            >
              {extra}
            </div>
          ) : undefined,
          children,
        },
      ]}
    />
  );
}
