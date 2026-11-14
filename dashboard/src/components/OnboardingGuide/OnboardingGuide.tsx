import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type ComponentType,
} from "react";
import { Button, Modal, Tour, type TourStepProps } from "antd";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Bot,
  Check,
  Cpu,
  Lightbulb,
  MessageSquare,
  Package,
  Radio,
  type LucideProps,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import cx from "classnames";

import { preferencesApi } from "../../api/modules/preferences";
import { useCurrentUser } from "../../hooks/useCurrentUser";
import { useIsMobile } from "../../hooks/useIsMobile";
import { navAllowed } from "../../utils/permissions";
import { publicUrl } from "../../utils/publicUrl";
import {
  buildOnboardingSteps,
  type OnboardingStep,
  type OnboardingStepKey,
} from "./onboardingSteps";
import styles from "./OnboardingGuide.module.less";

const STEP_ICONS: Record<OnboardingStepKey, ComponentType<LucideProps>> = {
  chat: MessageSquare,
  experts: Bot,
  models: Cpu,
  channels: Radio,
  knowledgeBases: BookOpen,
  skillPackages: Package,
};

/** Set on the spotlighted sidebar item so CSS can pulse it. */
const ACTIVE_ATTR = "data-onboarding-active";

type Phase = "intro" | "tour" | "done";

interface OnboardingGuideProps {
  open: boolean;
  onClose: () => void;
}

function navTarget(step: OnboardingStep): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-nav-key="${step.navKey}"]`);
}

/**
 * Welcome guide: an intro card, a spotlight tour that opens each page and
 * highlights its sidebar entry, then a short wrap-up.
 *
 * Leaving it at any point (finish, skip, close, Esc) marks it done for this
 * user on the server, so it does not open by itself again.
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
  const [phase, setPhase] = useState<Phase>("intro");
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    if (!open) return;
    setPhase("intro");
    setCurrent(0);
  }, [open]);

  const finish = useCallback(
    (path?: string) => {
      onClose();
      if (path) navigate(path);
      void preferencesApi
        .patch({ onboarding_completed: true })
        .catch(() => undefined);
    },
    [navigate, onClose],
  );

  const touring = open && phase === "tour";
  const step = steps[Math.min(current, steps.length - 1)];
  const isLast = current >= steps.length - 1;

  const goNext = useCallback(() => {
    if (isLast) setPhase("done");
    else setCurrent((i) => i + 1);
  }, [isLast]);
  const goBack = useCallback(() => {
    setCurrent((i) => Math.max(0, i - 1));
  }, []);

  // Open the step's page, then pulse its sidebar entry under the spotlight.
  useEffect(() => {
    if (!touring) return;
    navigate(step.path);
    const el = isMobile ? null : navTarget(step);
    el?.setAttribute(ACTIVE_ATTR, "");
    return () => el?.removeAttribute(ACTIVE_ATTR);
  }, [touring, step, navigate, isMobile]);

  useEffect(() => {
    if (!touring) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target instanceof Element ? e.target : null;
      if (el?.closest("input, textarea, [contenteditable=true]")) return;
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goBack();
      else if (e.key === "Escape") finish();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [touring, goNext, goBack, finish]);

  const tourSteps: TourStepProps[] = steps.map((s, i) => {
    const Icon = STEP_ICONS[s.key];
    const member = s.variant === "member";
    return {
      // Mobile keeps the nav in a closed drawer, so the card stays centered.
      target: isMobile ? null : () => navTarget(s) as HTMLElement,
      placement: isMobile ? "center" : "right",
      title: (
        <div key={`title-${i}`} className={styles.stepHead}>
          <span className={styles.stepIcon} aria-hidden>
            <Icon size={20} strokeWidth={1.8} />
          </span>
          <span>{t(`onboarding.steps.${s.key}.title`)}</span>
        </div>
      ),
      description: (
        <div key={`body-${i}`} className={styles.stepBody}>
          <p className={styles.stepText}>
            {t(`onboarding.steps.${s.key}.${member ? "bodyMember" : "body"}`)}
          </p>
          <p className={styles.stepTip}>
            <Lightbulb size={14} strokeWidth={1.8} aria-hidden />
            <span>
              {t(`onboarding.steps.${s.key}.${member ? "tipMember" : "tip"}`)}
            </span>
          </p>
        </div>
      ),
    };
  });

  const progressLabel = t("onboarding.progress", {
    current: current + 1,
    total: steps.length,
  });

  return (
    <>
      <Modal
        open={open && phase === "intro"}
        onCancel={() => finish()}
        footer={null}
        width={isMobile ? "calc(100vw - 32px)" : 560}
        centered
        destroyOnHidden
        className={styles.modal}
      >
        <div className={styles.intro}>
          <img
            src={publicUrl("octop-mascot-peek.webp")}
            alt=""
            className={styles.mascot}
            draggable={false}
          />
          <h3 className={styles.heroTitle}>{t("onboarding.intro.title")}</h3>
          <p className={styles.heroText}>{t("onboarding.intro.body")}</p>
          <ul className={styles.conceptGrid}>
            {steps.map((s, i) => {
              const Icon = STEP_ICONS[s.key];
              return (
                <li
                  key={s.key}
                  className={styles.concept}
                  style={{ "--i": i } as CSSProperties}
                >
                  <Icon size={18} strokeWidth={1.8} aria-hidden />
                  <span>{t(`onboarding.steps.${s.key}.title`)}</span>
                </li>
              );
            })}
          </ul>
          <div className={styles.introActions}>
            <Button
              type="primary"
              size="large"
              onClick={() => setPhase("tour")}
            >
              {t("onboarding.start")}
              <ArrowRight size={16} strokeWidth={2} />
            </Button>
            <Button type="text" onClick={() => finish()}>
              {t("onboarding.later")}
            </Button>
          </div>
          <span className={styles.duration}>
            {t("onboarding.intro.duration", { count: steps.length })}
            {!isMobile && ` · ${t("onboarding.keyboardHint")}`}
          </span>
        </div>
      </Modal>

      <Tour
        open={touring}
        current={current}
        onChange={setCurrent}
        onClose={() => finish()}
        steps={tourSteps}
        rootClassName={styles.tour}
        disabledInteraction
        gap={{ offset: 6, radius: 10 }}
        indicatorsRender={(cur, total) => (
          <div className={styles.tourProgress}>
            <div
              className={styles.tourBar}
              role="progressbar"
              aria-valuemin={1}
              aria-valuemax={total}
              aria-valuenow={cur + 1}
              aria-label={progressLabel}
            >
              <span
                className={styles.tourBarFill}
                style={{ width: `${((cur + 1) / total) * 100}%` }}
              />
            </div>
            <span className={styles.tourCount}>
              {cur + 1} / {total}
            </span>
          </div>
        )}
        actionsRender={() => (
          <div className={styles.tourActions}>
            <Button type="text" size="small" onClick={() => finish()}>
              {t("onboarding.skip")}
            </Button>
            {current > 0 && (
              <Button
                size="small"
                onClick={goBack}
                icon={<ArrowLeft size={14} />}
              >
                {t("onboarding.back")}
              </Button>
            )}
            <Button type="primary" size="small" onClick={goNext}>
              {isLast ? t("onboarding.finish") : t("onboarding.next")}
            </Button>
          </div>
        )}
      />

      <Modal
        open={open && phase === "done"}
        onCancel={() => finish()}
        footer={null}
        width={isMobile ? "calc(100vw - 32px)" : 440}
        centered
        destroyOnHidden
        className={styles.modal}
      >
        <div className={styles.done}>
          <div className={styles.burst} aria-hidden>
            {Array.from({ length: 12 }, (_, i) => (
              <span
                key={i}
                className={styles.spark}
                style={{ "--a": `${i * 30}deg` } as CSSProperties}
              />
            ))}
            <span className={styles.doneCheck}>
              <Check size={30} strokeWidth={2.4} />
            </span>
          </div>
          <h3 className={styles.heroTitle}>{t("onboarding.done.title")}</h3>
          <p className={styles.heroText}>{t("onboarding.done.body")}</p>
          <div className={cx(styles.introActions, styles.doneActions)}>
            <Button type="primary" size="large" onClick={() => finish("/chat")}>
              {t("onboarding.done.chat")}
            </Button>
            {navAllowed(user, "experts") && (
              <Button size="large" onClick={() => finish("/experts")}>
                {t("onboarding.done.experts")}
              </Button>
            )}
          </div>
        </div>
      </Modal>
    </>
  );
}
