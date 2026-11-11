import { useEffect, useMemo, useState, type ComponentType } from "react";
import { Button, Modal } from "antd";
import {
  BookOpen,
  Bot,
  Cpu,
  MessageSquare,
  Package,
  Radio,
  Sparkles,
  type LucideProps,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import cx from "classnames";

import { preferencesApi } from "../../api/modules/preferences";
import { useCurrentUser } from "../../hooks/useCurrentUser";
import { useIsMobile } from "../../hooks/useIsMobile";
import {
  buildOnboardingSteps,
  type OnboardingStepKey,
} from "./onboardingSteps";
import styles from "./OnboardingGuide.module.less";

const STEP_ICONS: Record<OnboardingStepKey, ComponentType<LucideProps>> = {
  welcome: Sparkles,
  chat: MessageSquare,
  experts: Bot,
  models: Cpu,
  channels: Radio,
  knowledgeBases: BookOpen,
  skillPackages: Package,
};

interface OnboardingGuideProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Welcome guide for the dashboard's main concepts.
 *
 * Closing it in any way (finish, skip, jump to a page, the close icon) marks it
 * done for this user on the server, so it does not open by itself again.
 */
export default function OnboardingGuide({
  open,
  onClose,
}: OnboardingGuideProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const user = useCurrentUser();
  const steps = useMemo(() => buildOnboardingSteps(user), [user]);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (open) setIndex(0);
  }, [open]);

  const step = steps[Math.min(index, steps.length - 1)];
  const isFirst = index === 0;
  const isLast = index >= steps.length - 1;
  const Icon = STEP_ICONS[step.key];

  const close = (path?: string) => {
    onClose();
    if (path) navigate(path);
    void preferencesApi
      .patch({ onboarding_completed: true })
      .catch(() => undefined);
  };

  const footer = (
    <div className={styles.footer}>
      {isLast ? (
        <span />
      ) : (
        <Button type="text" onClick={() => close()}>
          {t("onboarding.skip")}
        </Button>
      )}
      <div className={styles.footerNav}>
        {!isFirst && (
          <Button onClick={() => setIndex((i) => i - 1)}>
            {t("onboarding.back")}
          </Button>
        )}
        {isLast ? (
          <Button type="primary" onClick={() => close()}>
            {t("onboarding.finish")}
          </Button>
        ) : (
          <Button type="primary" onClick={() => setIndex((i) => i + 1)}>
            {isFirst ? t("onboarding.start") : t("onboarding.next")}
          </Button>
        )}
      </div>
    </div>
  );

  return (
    <Modal
      open={open}
      onCancel={() => close()}
      footer={footer}
      width={isMobile ? "calc(100vw - 32px)" : 520}
      centered
      destroyOnHidden
      title={null}
      className={styles.modal}
    >
      <div className={styles.body}>
        <div
          className={styles.progress}
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={steps.length}
          aria-valuenow={index + 1}
          aria-label={t("onboarding.progress", {
            current: index + 1,
            total: steps.length,
          })}
        >
          {steps.map((s, i) => (
            <span
              key={s.key}
              className={cx(styles.dot, i <= index && styles.dotActive)}
            />
          ))}
        </div>
        <div className={styles.icon} aria-hidden>
          <Icon size={28} strokeWidth={1.8} />
        </div>
        <h3 className={styles.title}>
          {t(`onboarding.steps.${step.key}.title`)}
        </h3>
        <p className={styles.text}>
          {t(`onboarding.steps.${step.key}.${step.bodyKey}`)}
        </p>
        {step.path && (
          <Button
            className={styles.goButton}
            onClick={() => close(step.path ?? undefined)}
          >
            {t(
              step.bodyKey === "bodyMember"
                ? `onboarding.steps.${step.key}.goMember`
                : `onboarding.steps.${step.key}.go`,
            )}
          </Button>
        )}
      </div>
    </Modal>
  );
}
