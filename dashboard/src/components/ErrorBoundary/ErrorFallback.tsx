import { OctopEmptyMascot } from "../EmptyState/OctopEmptyMascot";
import styles from "./ErrorFallback.module.less";

export interface ErrorFallbackAction {
  label: string;
  onClick: () => void;
  /** ``primary`` is the one action the page wants you to take. */
  variant?: "primary" | "default";
}

interface ErrorFallbackProps {
  title: string;
  subtitle: string;
  /** What the app actually threw. Hidden unless asked for — it is for a bug
   *  report, not for the person staring at the screen. */
  detail?: string | null;
  /** Label for the disclosure that hides ``detail``. */
  detailsLabel: string;
  /** Buttons, in reading order. */
  actions: ErrorFallbackAction[];
}

/**
 * Full-viewport failure surface: mascot, one title, one sentence, actions.
 *
 * It follows the same shape as the boot splash, the offline panel and the 404
 * page, because four failure renders that each invent their own layout is what
 * makes an app feel assembled from parts. The raw exception is deliberately
 * demoted into a disclosure — it used to be the subtitle, which meant a user
 * whose tab lost a chunk was greeted by "Failed to fetch dynamically imported
 * module".
 *
 * The buttons are plain ones rather than antd's: this component renders *above*
 * the ConfigProvider, so an antd Button here inherits none of the app's theme
 * and arrives in stock blue with the stock prefix. A crash page is the last
 * place that should look like a different product — and the last place worth
 * depending on the theme layer, which may itself be what broke.
 */
export default function ErrorFallback({
  title,
  subtitle,
  detail,
  detailsLabel,
  actions,
}: ErrorFallbackProps) {
  return (
    <div className={styles.wrap} role="alert">
      <div className={styles.inner}>
        <OctopEmptyMascot size={132} className={styles.mascot} />
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.subtitle}>{subtitle}</p>
        <div className={styles.actions}>
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              onClick={action.onClick}
              className={
                action.variant === "primary"
                  ? `${styles.button} ${styles.buttonPrimary}`
                  : styles.button
              }
            >
              {action.label}
            </button>
          ))}
        </div>
        {detail ? (
          <details className={styles.details}>
            <summary className={styles.summary}>{detailsLabel}</summary>
            <pre className={styles.detail}>{detail}</pre>
          </details>
        ) : null}
      </div>
    </div>
  );
}
