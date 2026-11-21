import cx from "classnames";

import styles from "./OctopSpinner.module.less";

interface OctopSpinnerProps {
  /** antd appends `${prefixCls}-dot` when this is the ConfigProvider indicator. */
  className?: string;
}

/**
 * Loading indicator wired globally as the antd Spin indicator: a faint
 * track with a short brand arc and an empty center. The logo splash stays
 * on the first-paint boot screen in index.html.
 */
export default function OctopSpinner({ className }: OctopSpinnerProps) {
  return (
    <span className={cx(styles.host, className)}>
      <span className={styles.track} />
      <span className={styles.ring} />
    </span>
  );
}
