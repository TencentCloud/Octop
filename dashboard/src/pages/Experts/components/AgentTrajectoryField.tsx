import { Form, Switch } from "antd";
import { useTranslation } from "react-i18next";

export default function AgentTrajectoryField({
  disabled = false,
}: {
  disabled?: boolean;
}) {
  const { t } = useTranslation();

  return (
    <Form.Item
      label={t("agentConfig.enableTrajectory")}
      name="enable_trajectory"
      valuePropName="checked"
      tooltip={t("agentConfig.enableTrajectoryTooltip")}
    >
      <Switch disabled={disabled} />
    </Form.Item>
  );
}
