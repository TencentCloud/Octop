import { Form, InputNumber } from "antd";
import { useTranslation } from "react-i18next";

export function AgentAdvancedConfigFields({
  requireLimits = false,
}: {
  /** When true, ``max_iters`` and ``max_input_length`` are required. */
  requireLimits?: boolean;
}) {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item
        label={t("agentConfig.maxIters")}
        name="max_iters"
        rules={
          requireLimits
            ? [
                {
                  required: true,
                  message: t("agentConfig.maxItersRequired"),
                },
                {
                  type: "number",
                  min: 1,
                  message: t("agentConfig.maxItersMin"),
                },
              ]
            : undefined
        }
        tooltip={t("agentConfig.maxItersTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={1}
          placeholder={t("agentConfig.maxItersPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.maxInputLength")}
        name="max_input_length"
        rules={
          requireLimits
            ? [
                {
                  required: true,
                  message: t("agentConfig.maxInputLengthRequired"),
                },
                {
                  type: "number",
                  min: 1000,
                  message: t("agentConfig.maxInputLengthMin"),
                },
              ]
            : undefined
        }
        tooltip={t("agentConfig.maxInputLengthTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={1000}
          step={1024}
          placeholder={t("agentConfig.maxInputLengthPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("experts.temperature")}
        name="temperature"
        tooltip={t("experts.temperatureTooltip")}
      >
        <InputNumber style={{ width: "100%" }} min={0} max={2} step={0.1} />
      </Form.Item>

      <Form.Item
        label={t("experts.topP")}
        name="top_p"
        tooltip={t("experts.topPTooltip")}
      >
        <InputNumber style={{ width: "100%" }} min={0} max={1} step={0.05} />
      </Form.Item>

      <Form.Item
        label={t("experts.maxTokens")}
        name="max_tokens"
        tooltip={t("experts.maxTokensTooltip")}
      >
        <InputNumber style={{ width: "100%" }} min={1} step={256} />
      </Form.Item>
    </>
  );
}
