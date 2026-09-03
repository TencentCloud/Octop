import styles from "./OctopSpinner.module.less";

const LOGO = `${import.meta.env.BASE_URL}logo.svg`;

interface OctopSpinnerProps {
  /** antd appends `${prefixCls}-dot` when this is the ConfigProvider indicator. */
  className?: string;
}

/**
 * Loading indicator matching the first-paint boot splash in index.html:
 * brand-colored ring around the breathing Octop logo. Wired globally as the
 * antd Spin indicator; only `size="large"` shows the logo.
 */
export default function OctopSpinner({ className }: OctopSpinnerProps) {
  return (
    <span className={[styles.host, className].filter(Boolean).join(" ")}>
      <span className={styles.ring} />
      <img
        className={styles.logo}
        src={LOGO}
        alt=""
        aria-hidden
        draggable={false}
      />
    </span>
  );
}
