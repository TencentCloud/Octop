import { useId, type ReactNode } from "react";
import cx from "classnames";

import styles from "./expertDrawer.module.less";

export default function ExpertDrawerSection({
  id,
  title,
  action,
  compact = false,
  children,
}: {
  id?: string;
  title?: ReactNode;
  action?: ReactNode;
  /** Less top rhythm — for trailing blocks (More settings) that follow content. */
  compact?: boolean;
  children: ReactNode;
}) {
  const reactId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const anchorId = id || `ed-section-${reactId}`;

  return (
    <section
      id={anchorId}
      className={cx(compact ? styles.sectionCompact : styles.section)}
    >
      {title ? <h4 className={styles.sectionTitle}>{title}</h4> : null}
      {action ? <div className={styles.sectionAction}>{action}</div> : null}
      <div className={styles.sectionBody}>{children}</div>
    </section>
  );
}
