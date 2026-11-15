import { useState } from "react";
import {
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Spin,
  Switch,
  Tooltip,
} from "antd";
import { MessageSquare } from "lucide-react";
import type { FormInstance } from "antd";
import cx from "classnames";
import { useTranslation } from "react-i18next";
import { acpApi } from "../../../../api/modules/acp";
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
import {
  isBuiltinRunner,
  runnerIcon,
  runnerIntroKey,
  runnerLabelKey,
} from "../constants";
import { AcpHostPanel } from "./AcpHostPanel";
import { AcpSectionToggle } from "./AcpSectionToggle";
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
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [asking, setAsking] = useState(false);
  const [askText, setAskText] = useState("");
  const [askError, setAskError] = useState("");
  const watchedCommand = Form.useWatch("command", form);
  const watchedArgs = Form.useWatch("argsText", form);
  const watchedEnv = Form.useWatch("envText", form);
  const titleName =
    !isCreateMode && activeKey
      ? isBuiltinRunner(activeKey)
        ? t(runnerLabelKey(activeKey))
        : activeKey
      : "";
  const intro =
    !isCreateMode && activeKey && isBuiltinRunner(activeKey)
      ? t(runnerIntroKey(activeKey))
      : "";

  const runAsk = async () => {
    setAsking(true);
    setAskText("");
    setAskError("");
    try {
      const result = await acpApi.askHost({
        runner: activeKey ?? String(form.getFieldValue("runnerKey") || ""),
        command: String(form.getFieldValue("command") || "").trim(),
        args: parseArgsText(form.getFieldValue("argsText")),
        env: parseEnvText(form.getFieldValue("envText")),
      });
      if (result.ok) {
        setAskText(result.text);
      } else {
        setAskError(
          result.detail ||
            t(`acp.host.reason.${result.reason}`, {
              defaultValue: t("acp.askFailed"),
            }),
        );
      }
    } catch (err) {
      setAskError(err instanceof Error ? err.message : String(err));
    } finally {
      setAsking(false);
    }
  };

  const runnerKeyField = (
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
  );

  return (
    <Drawer
      title={
        isCreateMode ? (
          t("acp.createTitle")
        ) : (
          <span className={styles.drawerTitle}>
            {activeKey ? (
              <img
                src={runnerIcon(activeKey)}
                alt=""
                className={cx(
                  styles.drawerTitleIcon,
                  activeKey === "pi" && styles.invertOnDark,
                )}
              />
            ) : null}
            <span>
              {titleName
                ? `${t("acp.editTitle")}: ${titleName}`
                : t("acp.editTitle")}
            </span>
          </span>
        )
      }
      open={open}
      onClose={onClose}
      width={560}
      destroyOnHidden
      afterOpenChange={(next) => {
        if (!next) return;
        setAdvancedOpen(false);
        setAsking(false);
        setAskText("");
        setAskError("");
      }}
      footer={
        <div className={styles.drawerFooterWrap}>
          {asking || askText || askError ? (
            <div className={styles.askBar}>
              <div className={styles.askResultLabel}>{t("acp.askResult")}</div>
              {asking && !askText ? <Spin size="small" /> : null}
              {askText ? (
                <pre className={styles.askOutput}>{askText}</pre>
              ) : null}
              {askError ? <p className={styles.askError}>{askError}</p> : null}
            </div>
          ) : null}
          <div className={styles.drawerFooter}>
            <div>
              {canDelete ? (
                <Button danger onClick={onDelete}>
                  {t("common.delete")}
                </Button>
              ) : null}
            </div>
            <div className={styles.drawerFooterActions}>
              <Tooltip title={t("acp.askHint")}>
                <Button
                  icon={<MessageSquare size={14} />}
                  loading={asking}
                  onClick={() => void runAsk()}
                >
                  {t("acp.askProbe")}
                </Button>
              </Tooltip>
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
        </div>
      }
    >
      <Form form={form} layout="vertical" onFinish={onSubmit}>
        {intro ? <p className={styles.drawerIntro}>{intro}</p> : null}
        {isCreateMode ? (
          <p className={styles.drawerHint}>{t("acp.docsHint")}</p>
        ) : (
          <AcpHostPanel
            open={open}
            runner={activeKey ?? ""}
            command={String(watchedCommand ?? "")}
            argsText={String(watchedArgs ?? "")}
            envText={String(watchedEnv ?? "")}
          />
        )}

        <div className={styles.switchRow}>
          <div>
            <div className={styles.switchLabel}>{t("common.enabled")}</div>
            {!isCreateMode ? (
              <div className={styles.switchHelp}>
                {t("acp.disableKeepsRunner")}
              </div>
            ) : null}
          </div>
          <Form.Item name="enabled" valuePropName="checked" noStyle>
            <Switch />
          </Form.Item>
        </div>

        {runnerKeyField}

        <AcpSectionToggle
          label={t("acp.advanced")}
          open={advancedOpen}
          onToggle={() => setAdvancedOpen((current) => !current)}
        >
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
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} />
          </Form.Item>
          <Form.Item
            name="envText"
            label={t("acp.env")}
            tooltip={t("acp.envHelp")}
          >
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} />
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
        </AcpSectionToggle>
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
