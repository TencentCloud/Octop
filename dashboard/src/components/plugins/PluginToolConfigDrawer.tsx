import { useState } from "react";
import { Button, Drawer, Form, Input, InputNumber } from "antd";
import { useTranslation } from "react-i18next";
import {
  pluginsApi,
  type AgentPluginTool,
  type PluginConfigField,
} from "../../api/modules/plugins";
import { message } from "../../utils/antdMessage";
import { apiErrorMessage } from "../../utils/apiError";

function configField(field: PluginConfigField) {
  const props = {
    label: field.label || field.name,
    name: field.name,
    rules: field.required
      ? [{ required: true, message: field.label || field.name }]
      : undefined,
    extra: field.help,
  };
  if (field.type === "password") {
    return (
      <Form.Item key={field.name} {...props}>
        <Input.Password placeholder={field.placeholder} autoComplete="off" />
      </Form.Item>
    );
  }
  if (field.type === "number") {
    return (
      <Form.Item key={field.name} {...props}>
        <InputNumber
          style={{ width: "100%" }}
          placeholder={field.placeholder}
        />
      </Form.Item>
    );
  }
  return (
    <Form.Item key={field.name} {...props}>
      <Input placeholder={field.placeholder} />
    </Form.Item>
  );
}

interface PluginToolConfigDrawerProps {
  agentId: string;
  tool: AgentPluginTool;
  onClose: () => void;
  onSaved: (config: Record<string, unknown>) => void;
}

export default function PluginToolConfigDrawer({
  agentId,
  tool,
  onClose,
  onSaved,
}: PluginToolConfigDrawerProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const save = async (values: Record<string, unknown>) => {
    const config = { ...tool.config, ...values };
    setSaving(true);
    try {
      await pluginsApi.patchAgentTools(agentId, {
        [tool.plugin_id]: { tools: { [tool.name]: { config } } },
      });
      message.success(t("plugins.saved"));
      onSaved(config);
    } catch (error) {
      message.error(apiErrorMessage(error, t("plugins.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      title={tool.name}
      open
      onClose={onClose}
      width={420}
      extra={
        <Button type="primary" loading={saving} onClick={() => form.submit()}>
          {t("common.save")}
        </Button>
      }
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={tool.config}
        onFinish={save}
      >
        {tool.config_fields.map(configField)}
      </Form>
    </Drawer>
  );
}
