import type { ReactNode } from "react";
import { Button, Tooltip } from "antd";

import styles from "./StreamSetupGuide.module.less";

export interface SetupGuideStep {
  label: string;
  detail?: string;
}

export interface SetupGuideAction {
  label: ReactNode;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  type?: "primary" | "default";
  danger?: boolean;
  title?: string;
}

interface StreamSetupGuideProps {
  icon: ReactNode;
  title: string;
  description?: string;
  steps: SetupGuideStep[];
  primaryAction?: SetupGuideAction;
  secondaryAction?: SetupGuideAction;
  /** Optional third action (e.g. uninstall) rendered after the main pair. */
  extraAction?: SetupGuideAction;
  className?: string;
  /** Widen the card for longer explanatory copy. */
  wide?: boolean;
}

function ActionButton({ action }: { action: SetupGuideAction }) {
  const button = (
    <Button
      type={action.type ?? "primary"}
      danger={action.danger}
      icon={action.icon}
      loading={action.loading}
      disabled={action.disabled}
      onClick={action.onClick}
    >
      {action.label}
    </Button>
  );
  if (!action.title) return button;
  return <Tooltip title={action.title}>{button}</Tooltip>;
}

export default function StreamSetupGuide({
  icon,
  title,
  description,
  steps,
  primaryAction,
  secondaryAction,
  extraAction,
  className,
  wide,
}: StreamSetupGuideProps) {
  const hasActions = primaryAction || secondaryAction || extraAction;
  const wrapClass = [styles.wrap, wide ? styles.wide : "", className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={wrapClass}>
      <div className={styles.card}>
        <div className={styles.icon}>{icon}</div>
        <h3 className={styles.title}>{title}</h3>
        {description ? (
          <p className={styles.description}>{description}</p>
        ) : null}
        {steps.length > 0 ? (
          <ol className={styles.steps}>
            {steps.map((step, index) => (
              <li key={index} className={styles.step}>
                <span className={styles.stepIndex}>{index + 1}</span>
                <div className={styles.stepBody}>
                  <div className={styles.stepLabel}>{step.label}</div>
                  {step.detail ? (
                    <div className={styles.stepDetail}>{step.detail}</div>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        ) : null}
        {hasActions ? (
          <div className={styles.actions}>
            {primaryAction ? <ActionButton action={primaryAction} /> : null}
            {secondaryAction ? <ActionButton action={secondaryAction} /> : null}
            {extraAction ? <ActionButton action={extraAction} /> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
