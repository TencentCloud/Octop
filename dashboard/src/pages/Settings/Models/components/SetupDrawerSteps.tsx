/**
 * Lightweight step cue for create-provider drawers (embedding / presets).
 */
import { Steps } from "antd";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

interface SetupDrawerStepsProps {
  /** 0 = credentials, 1 = models, 2 = ready to test/create */
  current: number;
}

export function SetupDrawerSteps({ current }: SetupDrawerStepsProps) {
  const { t } = useTranslation();
  return (
    <div className={styles.setupSteps}>
      <Steps
        size="small"
        current={Math.min(Math.max(current, 0), 2)}
        items={[
          { title: t("models.setupStepCredentials") },
          { title: t("models.setupStepModels") },
          { title: t("models.setupStepReady") },
        ]}
      />
    </div>
  );
}
