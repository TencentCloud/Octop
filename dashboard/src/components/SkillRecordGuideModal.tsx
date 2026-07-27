/**
 * Skill Record Guide Modal — onboarding popup for browser skill recording.
 *
 * Displayed in the Remote Browser page. Shows a brief walkthrough of the
 * recording workflow. No input fields here — the user fills in the task
 * objective and operation description in the AI chat panel after recording
 * starts.
 */
import { useState } from "react";
import { Modal, Button, Steps, Typography, Space, Alert } from "antd";
import { useTranslation } from "react-i18next";
import { Sparkles, ArrowRight } from "lucide-react";

interface SkillRecordGuideModalProps {
  open: boolean;
  onCancel: () => void;
  /** Callback when user clicks "start recording" — no payload, just triggers the flow */
  onStartRecording: () => void;
  /** Whether browser env is ready */
  envReady: boolean;
}

export default function SkillRecordGuideModal({
  open,
  onCancel,
  onStartRecording,
  envReady,
}: SkillRecordGuideModalProps) {
  const { t } = useTranslation();
  const [currentStep, setCurrentStep] = useState(0);

  const stepItems = [
    {
      title: t("skillRecordGuide.step1Title", "开始录制"),
      description: t(
        "skillRecordGuide.step1Desc",
        "点击下方按钮，系统将开始录制所有浏览器操作。",
      ),
    },
    {
      title: t("skillRecordGuide.step2Title", "输入任务目标"),
      description: t(
        "skillRecordGuide.step2Desc",
        '录制开始后，AI助手会提示你输入任务目标——这将成为技能的名称和触发关键词（例如"登录OA系统"）。',
      ),
    },
    {
      title: t("skillRecordGuide.step3Title", "描述操作步骤"),
      description: t(
        "skillRecordGuide.step3Desc",
        "接着描述你想让AI助手在浏览器中执行的操作，助手会自动执行并录制。",
      ),
    },
    {
      title: t("skillRecordGuide.step4Title", "结束录制并确认"),
      description: t(
        "skillRecordGuide.step4Desc",
        '操作完成后，输入"结束"停止录制，确认后技能将以任务目标为名保存。之后只需输入任务目标关键词即可触发回放。',
      ),
    },
  ];

  const handleStart = () => {
    setCurrentStep(0);
    onStartRecording();
  };

  const handleClose = () => {
    setCurrentStep(0);
    onCancel();
  };

  return (
    <Modal
      title={
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Sparkles
            size={18}
            style={{ color: "var(--fn-color-brand, #635bff)" }}
          />
          <span>{t("skillRecordGuide.title", "技能录制引导")}</span>
        </div>
      }
      open={open}
      onCancel={handleClose}
      width={520}
      footer={
        <Space>
          <Button onClick={handleClose}>{t("common.cancel", "取消")}</Button>
          <Button
            type="primary"
            icon={<ArrowRight size={14} />}
            onClick={handleStart}
            disabled={!envReady}
          >
            {envReady
              ? t("skillRecordGuide.startRecording", "开始录制")
              : t("skillRecordGuide.envNotReady", "请先安装浏览器环境")}
          </Button>
        </Space>
      }
      destroyOnHidden
    >
      <div style={{ padding: "8px 0" }}>
        <Typography.Paragraph
          style={{
            fontSize: 14,
            color: "var(--fn-text-secondary)",
            marginBottom: 16,
          }}
        >
          {t(
            "skillRecordGuide.intro",
            "通过录制浏览器操作，自动生成可复用的技能脚本。录制开始后，你将在AI助手对话中输入任务目标和操作描述。",
          )}
        </Typography.Paragraph>

        <Steps
          current={currentStep}
          onChange={setCurrentStep}
          direction="vertical"
          size="small"
          items={stepItems.map((item) => ({
            title: item.title,
            description: item.description,
          }))}
          style={{ marginBottom: 8 }}
        />

        {!envReady && (
          <Alert
            type="warning"
            showIcon
            message={t("skillRecordGuide.envWarning", "浏览器环境未就绪")}
            description={t(
              "skillRecordGuide.envWarningDesc",
              "请先确保浏览器环境可用，然后再开始录制。",
            )}
            style={{ marginBottom: 8 }}
          />
        )}
      </div>
    </Modal>
  );
}
