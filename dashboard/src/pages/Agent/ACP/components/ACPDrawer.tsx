import { Button, Drawer, Form, Input, InputNumber, Select, Switch } from "antd";
import type { FormInstance } from "antd";
import { useTranslation } from "react-i18next";
import type {
  ACPToolParseMode,
  ACPRunnerConfig,
} from "../../../../api/types/acp";
import {
  parseArgsText,
  parseEnvText,
  stringifyArgs,
  stringifyEnv,
} from "../../../../api/types/acp";
import styles from "../index.module.less";

const PARSE_MODES: { value: ACPToolParseMode; label: string }[] = [
  { value: "call_title", label: "call_title" },
  { value: "update_detail", label: "update_detail" },
  { value: "call_detail", label: "call_detail" },
];

interface ACPDrawerProps {
  open: boolean;
  activeKey: string | null;
  isCreateMode?: boolean;
  form: FormInstance;
  saving: boolean;
  canEditKey?: boolean;
  canDelete?: boolean;
  onClose: () => void;
  onSubmit: (values: Record<string, unknown>) => void;
  onDelete?: () => void;
}

export function ACPDrawer({
  open,
  activeKey,
  isCreateMode = false,
  form,
  saving,
  canEditKey = false,
  canDelete = false,
  onClose,
  onSubmit,
  onDelete,
}: ACPDrawerProps) {
  const { t } = useTranslation();

  return (
    <Drawer
      title={
        isCreateMode
          ? t("acp.createTitle")
          : activeKey
          ? `${t("acp.editTitle")}: ${activeKey}`
          : t("acp.editTitle")
      }
      open={open}
      onClose={onClose}
      width={520}
      destroyOnHidden
      footer={
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <div>
            {canDelete ? (
              <Button danger onClick={onDelete}>
                {t("common.delete")}
              </Button>
            ) : null}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            <Button
              type="primary"
              loading={saving}
              onClick={() => form.submit()}
            >
              {t("common.save")}
            </Button>
          </div>
        </div>
      }
    >
      <Form form={form} layout="vertical" onFinish={onSubmit}>
        <Form.Item
          name="runnerKey"
          label={t("acp.runnerKey")}
          rules={[
            { required: true, message: t("acp.runnerKeyRequired") },
            { pattern: /^[A-Za-z0-9_-]+$/, message: t("acp.runnerKeyInvalid") },
          ]}
        >
          <Input placeholder="my_custom_runner" disabled={!canEditKey} />
        </Form.Item>
        <Form.Item
          name="enabled"
          label={t("common.enabled")}
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
        <Form.Item
          name="command"
          label={t("acp.command")}
          rules={[{ required: true, message: t("acp.commandRequired") }]}
        >
          <Input placeholder="opencode" />
        </Form.Item>
        <Form.Item
          name="argsText"
          label={t("acp.args")}
          tooltip={t("acp.argsHelp")}
        >
          <Input.TextArea autoSize={{ minRows: 4, maxRows: 8 }} />
        </Form.Item>
        <Form.Item
          name="envText"
          label={t("acp.env")}
          tooltip={t("acp.envHelp")}
        >
          <Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} />
        </Form.Item>
        <Form.Item
          name="trusted"
          label={t("acp.trusted")}
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
        <Form.Item name="tool_parse_mode" label={t("acp.toolParseMode")}>
          <Select options={PARSE_MODES} />
        </Form.Item>
        <Form.Item
          name="stdio_buffer_limit_bytes"
          label={t("acp.stdioBufferLimit")}
        >
          <InputNumber style={{ width: "100%" }} min={1} step={1024} />
        </Form.Item>
        <p className={styles.drawerHint}>{t("acp.docsHint")}</p>
      </Form>
    </Drawer>
  );
}

export function formValuesToRunner(
  values: Record<string, unknown>,
): ACPRunnerConfig {
  return {
    enabled: Boolean(values.enabled),
    command: String(values.command || ""),
    args: parseArgsText(values.argsText),
    env: parseEnvText(values.envText),
    trusted: Boolean(values.trusted),
    tool_parse_mode:
      (values.tool_parse_mode as ACPToolParseMode) || "update_detail",
    stdio_buffer_limit_bytes:
      Number(values.stdio_buffer_limit_bytes) || 50 * 1024 * 1024,
  };
}

export function runnerToFormValues(
  key: string,
  config: ACPRunnerConfig,
): Record<string, unknown> {
  return {
    runnerKey: key,
    ...config,
    argsText: stringifyArgs(config.args),
    envText: stringifyEnv(config.env),
  };
}
