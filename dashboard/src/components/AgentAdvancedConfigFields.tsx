import { Form, InputNumber, Switch } from "antd";
import type { ReactNode } from "react";
import styles from "./AgentAdvancedConfigFields.module.less";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

const RETRY_GROUPS = {
  modelRetry: {
    enabledName: "model_retry_enabled",
    retriesName: "model_retry_max_retries",
    initialName: "model_retry_initial_delay",
    maxName: "model_retry_max_delay",
  },
  toolRetry: {
    enabledName: "tool_retry_enabled",
    retriesName: "tool_retry_max_retries",
    initialName: "tool_retry_initial_delay",
    maxName: "tool_retry_max_delay",
  },
} as const;

type RetryGroup = keyof typeof RETRY_GROUPS;

const RETRY_COPY_KEYS = [
  "enabled",
  "enabledTooltip",
  "maxRetries",
  "maxRetriesTooltip",
  "maxRetriesPlaceholder",
  "initialDelay",
  "initialDelayTooltip",
  "initialDelayPlaceholder",
  "maxDelay",
  "maxDelayTooltip",
  "maxDelayPlaceholder",
] as const;

function retryCopy(group: RetryGroup, t: TFunction) {
  return Object.fromEntries(
    RETRY_COPY_KEYS.map((key) => [key, t(`agentConfig.${group}.${key}`)]),
  ) as Record<(typeof RETRY_COPY_KEYS)[number], string>;
}

function delayWindowRule(
  t: TFunction,
  enabledName: string,
  initialName: string,
  maxName: string,
) {
  return ({ getFieldValue }: { getFieldValue: (name: string) => unknown }) => ({
    validator() {
      if (getFieldValue(enabledName) === false) return Promise.resolve();
      const initial = getFieldValue(initialName);
      const maximum = getFieldValue(maxName);
      const initialValue = typeof initial === "number" ? initial : 1;
      const maximumValue = typeof maximum === "number" ? maximum : 60;
      if (maximumValue < initialValue) {
        return Promise.reject(
          new Error(t("agentConfig.retryDelayBelowInitial")),
        );
      }
      return Promise.resolve();
    },
  });
}

function RuntimeGroup({
  title,
  children,
  grouped,
}: {
  title: string;
  children: ReactNode;
  grouped: boolean;
}) {
  if (!grouped) return <>{children}</>;
  return (
    <fieldset className={styles.group}>
      <legend>{title}</legend>
      {children}
    </fieldset>
  );
}

function RetryBudgetFields({
  group,
  grouped,
}: {
  group: RetryGroup;
  grouped: boolean;
}) {
  const { t } = useTranslation();
  const fields = RETRY_GROUPS[group];
  const copy = retryCopy(group, t);
  const enabled = Form.useWatch(fields.enabledName);
  const disabled = enabled === false;
  const delayRule = delayWindowRule(
    t,
    fields.enabledName,
    fields.initialName,
    fields.maxName,
  );

  return (
    <RuntimeGroup
      grouped={grouped}
      title={t(`agentConfig.runtimeGroups.${group}`)}
    >
      <Form.Item
        label={copy.enabled}
        name={fields.enabledName}
        valuePropName="checked"
        initialValue={true}
        tooltip={copy.enabledTooltip}
      >
        <Switch />
      </Form.Item>
      <Form.Item
        label={copy.maxRetries}
        name={fields.retriesName}
        tooltip={copy.maxRetriesTooltip}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={0}
          step={1}
          disabled={disabled}
          placeholder={copy.maxRetriesPlaceholder}
        />
      </Form.Item>
      <Form.Item
        label={copy.initialDelay}
        name={fields.initialName}
        dependencies={[fields.maxName, fields.enabledName]}
        tooltip={copy.initialDelayTooltip}
        rules={[delayRule]}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={0.1}
          step={0.1}
          disabled={disabled}
          placeholder={copy.initialDelayPlaceholder}
        />
      </Form.Item>
      <Form.Item
        label={copy.maxDelay}
        name={fields.maxName}
        dependencies={[fields.initialName, fields.enabledName]}
        tooltip={copy.maxDelayTooltip}
        rules={[delayRule]}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={0.1}
          step={1}
          disabled={disabled}
          placeholder={copy.maxDelayPlaceholder}
        />
      </Form.Item>
    </RuntimeGroup>
  );
}

export function AgentAdvancedConfigFields({
  requireLimits = false,
  grouped = false,
}: {
  /** When true, ``max_iters`` and ``max_input_length`` are required. */
  requireLimits?: boolean;
  grouped?: boolean;
}) {
  const { t } = useTranslation();
  const compactionEnabled = Form.useWatch(["compaction", "enabled"]);
  const toolCallLimitEnabled = Form.useWatch("tool_call_limit_enabled");

  return (
    <>
      <RuntimeGroup
        grouped={grouped}
        title={t("agentConfig.runtimeGroups.modelLimits")}
      >
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
      </RuntimeGroup>
      <RuntimeGroup
        grouped={grouped}
        title={t("agentConfig.runtimeGroups.toolCallLimit")}
      >
        <Form.Item
          label={t("agentConfig.toolCallLimit.enabled")}
          name="tool_call_limit_enabled"
          valuePropName="checked"
          initialValue={true}
          tooltip={t("agentConfig.toolCallLimit.enabledTooltip")}
        >
          <Switch />
        </Form.Item>

        <Form.Item
          label={t("agentConfig.toolCallLimit.runLimit")}
          name="tool_call_run_limit"
          tooltip={t("agentConfig.toolCallLimit.runLimitTooltip")}
        >
          <InputNumber
            style={{ width: "100%" }}
            min={1}
            step={1}
            disabled={toolCallLimitEnabled === false}
            placeholder={t("agentConfig.toolCallLimit.runLimitPlaceholder")}
          />
        </Form.Item>
      </RuntimeGroup>
      <RetryBudgetFields grouped={grouped} group="modelRetry" />
      <RetryBudgetFields grouped={grouped} group="toolRetry" />

      <RuntimeGroup
        grouped={grouped}
        title={t("agentConfig.runtimeGroups.compaction")}
      >
        <Form.Item
          label={t("agentConfig.compaction.enabled")}
          name={["compaction", "enabled"]}
          valuePropName="checked"
          initialValue={true}
          tooltip={t("agentConfig.compaction.enabledTooltip")}
        >
          <Switch />
        </Form.Item>

        <Form.Item
          label={t("agentConfig.compaction.trigger")}
          name={["compaction", "trigger_fraction"]}
          tooltip={t("agentConfig.compaction.triggerTooltip")}
        >
          <InputNumber
            style={{ width: "100%" }}
            min={0.01}
            max={1}
            step={0.05}
            disabled={compactionEnabled === false}
            placeholder={t("agentConfig.compaction.triggerPlaceholder")}
          />
        </Form.Item>

        <Form.Item
          label={t("agentConfig.compaction.keep")}
          name={["compaction", "keep_fraction"]}
          dependencies={[["compaction", "trigger_fraction"]]}
          tooltip={t("agentConfig.compaction.keepTooltip")}
          rules={[
            ({ getFieldValue }) => ({
              validator(_, value: unknown) {
                if (typeof value !== "number") return Promise.resolve();
                const trigger = getFieldValue([
                  "compaction",
                  "trigger_fraction",
                ]);
                const limit = typeof trigger === "number" ? trigger : 0.85;
                if (value >= limit) {
                  return Promise.reject(
                    new Error(t("agentConfig.compaction.keepBelowTrigger")),
                  );
                }
                return Promise.resolve();
              },
            }),
          ]}
        >
          <InputNumber
            style={{ width: "100%" }}
            min={0.01}
            max={0.99}
            step={0.05}
            disabled={compactionEnabled === false}
            placeholder={t("agentConfig.compaction.keepPlaceholder")}
          />
        </Form.Item>

        <Form.Item
          label={t("agentConfig.compaction.trim")}
          name={["compaction", "trim_tokens"]}
          tooltip={t("agentConfig.compaction.trimTooltip")}
        >
          <InputNumber
            style={{ width: "100%" }}
            min={1000}
            step={1000}
            disabled={compactionEnabled === false}
            placeholder={t("agentConfig.compaction.trimPlaceholder")}
          />
        </Form.Item>
      </RuntimeGroup>
    </>
  );
}
