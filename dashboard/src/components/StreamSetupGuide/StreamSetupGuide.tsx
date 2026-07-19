import type { ReactNode } from "react";
import { Button } from "antd";

import styles from "./StreamSetupGuide.module.less";

export interface SetupGuideStep {
  label: string;
  detail?: string;
}

export interface SetupGuideAction {
  label: string;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  type?: "primary" | "default";
  danger?: boolean;
}

interface StreamSetupGuideProps {
  icon: ReactNode;
  title: string;
  description?: string;
  steps: SetupGuideStep[];
  primaryAction?: SetupGuideAction;
  secondaryAction?: SetupGuideAction;
}

export default function StreamSetupGuide({
  icon,
  title,
  description,
  steps,
  primaryAction,
  secondaryAction,
}: StreamSetupGuideProps) {
  return (
    <div className={styles.wrap}>
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
        {primaryAction || secondaryAction ? (
          <div className={styles.actions}>
            {primaryAction ? (
              <Button
                type={primaryAction.type ?? "primary"}
                danger={primaryAction.danger}
                icon={primaryAction.icon}
                loading={primaryAction.loading}
                disabled={primaryAction.disabled}
                onClick={primaryAction.onClick}
              >
                {primaryAction.label}
              </Button>
            ) : null}
            {secondaryAction ? (
              <Button
                type={secondaryAction.type ?? "default"}
                danger={secondaryAction.danger}
                icon={secondaryAction.icon}
                loading={secondaryAction.loading}
                disabled={secondaryAction.disabled}
                onClick={secondaryAction.onClick}
              >
                {secondaryAction.label}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
