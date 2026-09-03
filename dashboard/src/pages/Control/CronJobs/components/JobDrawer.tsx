import { useEffect, useMemo, useState } from "react";
import {
  Drawer,
  Form,
  Input,
  Select,
  Switch,
  Button,
  Divider,
  Typography,
} from "antd";
import { useTranslation } from "react-i18next";
import type { FormInstance } from "antd";
import { providerApi } from "../../../../api/modules/provider";
import { connectorsApi } from "../../../../api/modules/connectors";
import { octopThreadsApi } from "../../../../api/modules/octopThreads";
import {
  buildDefaultFormValues,
  SCHEDULE_PRESETS,
  cronToPreset,
  presetToCron,
} from "./constants";
import { CRON_NAME_MAX_LEN, CRON_PROMPT_MAX_LEN } from "../constants";
import { channelFromSessionKey } from "../cronDisplay";
import type { CronJobFormValues } from "../useCronJobs";
import {
  buildModelSelectOptions,
  defaultModelToForm,
  MODEL_AUTO_VALUE,
  type ModelPickerOption,
} from "../../../../utils/modelOptions";

const { Text } = Typography;

interface JobDrawerProps {
  open: boolean;
  editingJob: CronJobFormValues | null;
  activeAgentId: string | null;
  cronTimezone: string;
  form: FormInstance<CronJobFormValues>;
  onClose: () => void;
  onSubmit: (values: CronJobFormValues) => void;
}

function SectionHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div style={{ marginBottom: 16 }}>
      <Divider
        orientation="left"
        orientationMargin={0}
        style={{ marginBottom: 4, fontSize: 14, fontWeight: 600 }}
      >
        {title}
      </Divider>
      {description && (
        <Text
          type="secondary"
          style={{
            fontSize: 12,
            lineHeight: 1.5,
            display: "block",
            marginBottom: 4,
          }}
        >
          {description}
        </Text>
      )}
    </div>
  );
}

export function JobDrawer({
  open,
  editingJob,
  activeAgentId,
  cronTimezone,
  form,
  onClose,
  onSubmit,
}: JobDrawerProps) {
  const { t } = useTranslation();
  const scheduleMode = Form.useWatch("_scheduleMode", form);
  const freshThread = Form.useWatch("fresh_thread", form);

  const [models, setModels] = useState<ModelPickerOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [sessionOptions, setSessionOptions] = useState<
    Array<{ label: string; value: string }>
  >([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [connectorOptions, setConnectorOptions] = useState<
    Array<{ label: string; value: string }>
  >([]);
  const [connectorsLoading, setConnectorsLoading] = useState(false);

  const presetOptions = useMemo(
    () =>
      SCHEDULE_PRESETS.map((p) => ({
        value: p.value,
        label: `${t(p.labelKey)} (${p.cron})`,
      })),
    [t],
  );

  useEffect(() => {
    if (!open) return;
    if (editingJob) {
      const matchedPreset = cronToPreset(editingJob.schedule?.cron || "");
      form.setFieldsValue({
        ...editingJob,
        model: defaultModelToForm(editingJob.model),
        _scheduleMode: matchedPreset ? "preset" : "custom",
        _preset: matchedPreset || editingJob._preset || "daily_9am",
      });
    } else {
      form.resetFields();
      form.setFieldsValue(buildDefaultFormValues(cronTimezone));
    }
  }, [open, editingJob, cronTimezone, form]);

  useEffect(() => {
    if (!open) return;
    setModelsLoading(true);
    void providerApi
      .listResolvedModels()
      .then((data) => setModels((data || []) as ModelPickerOption[]))
      .catch(() => setModels([]))
      .finally(() => setModelsLoading(false));
  }, [open]);

  useEffect(() => {
    if (!open || !activeAgentId) {
      setSessionOptions([]);
      return;
    }
    setSessionsLoading(true);
    octopThreadsApi
      .list(activeAgentId, 100)
      .then((threads) => {
        const seen = new Set<string>();
        const options: Array<{ label: string; value: string }> = [];
        for (const th of threads || []) {
          if (!th.session_key || seen.has(th.session_key)) continue;
          seen.add(th.session_key);
          const channel = channelFromSessionKey(th.session_key);
          const title = th.title?.trim();
          options.push({
            value: th.session_key,
            label: title
              ? `${channel} · ${title}`
              : `${channel} · ${th.session_key}`,
          });
        }
        setSessionOptions(options);
      })
      .catch(() => setSessionOptions([]))
      .finally(() => setSessionsLoading(false));
  }, [open, activeAgentId]);

  useEffect(() => {
    if (!open) {
      setConnectorOptions([]);
      return;
    }
    setConnectorsLoading(true);
    void connectorsApi
      .listInstances()
      .then((instances) => {
        setConnectorOptions(
          (instances || []).map((i) => ({
            value: i.mcp_server_name,
            label: i.display_name?.trim()
              ? `${i.display_name} (${i.mcp_server_name})`
              : i.mcp_server_name,
          })),
        );
      })
      .catch(() => setConnectorOptions([]))
      .finally(() => setConnectorsLoading(false));
  }, [open]);

  const modelOptions = buildModelSelectOptions(
    models,
    t("experts.defaultModelAuto"),
  );

  return (
    <Drawer
      width={520}
      placement="right"
      title={editingJob ? t("cronJobs.editJob") : t("cronJobs.createJob")}
      open={open}
      onClose={onClose}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onSubmit}
        initialValues={buildDefaultFormValues(cronTimezone)}
      >
        <SectionHeader
          title={t("cronJobs.form.sectionBasic")}
          description={t("cronJobs.form.sectionBasicDesc")}
        />

        {editingJob?.id && (
          <Form.Item
            name="id"
            label={t("cronJobs.form.id")}
            tooltip={t("cronJobs.form.idTooltip")}
          >
            <Input disabled />
          </Form.Item>
        )}

        <Form.Item
          name="name"
          label={t("cronJobs.form.name")}
          rules={[
            { required: true, message: t("cronJobs.pleaseInputName") },
            {
              max: CRON_NAME_MAX_LEN,
              message: t("cronJobs.form.nameTooLong", {
                max: CRON_NAME_MAX_LEN,
              }),
            },
          ]}
          tooltip={t("cronJobs.form.nameTooltip")}
        >
          <Input
            maxLength={CRON_NAME_MAX_LEN}
            showCount
            placeholder={t("cronJobs.jobNamePlaceholder")}
          />
        </Form.Item>

        <Form.Item
          name="enabled"
          label={t("cronJobs.form.enabled")}
          valuePropName="checked"
          tooltip={t("cronJobs.form.enabledTooltip")}
        >
          <Switch />
        </Form.Item>

        <SectionHeader
          title={t("cronJobs.form.sectionSchedule")}
          description={t("cronJobs.form.sectionScheduleDesc")}
        />

        <Form.Item name={["schedule", "type"]} hidden>
          <Input />
        </Form.Item>

        <Form.Item
          name="_scheduleMode"
          label={t("cronJobs.form.scheduleMode")}
          tooltip={t("cronJobs.form.scheduleModeTooltip")}
        >
          <Select>
            <Select.Option value="preset">
              {t("cronJobs.form.scheduleModePreset")}
            </Select.Option>
            <Select.Option value="custom">
              {t("cronJobs.form.scheduleModeCustom")}
            </Select.Option>
          </Select>
        </Form.Item>

        {scheduleMode === "preset" ? (
          <Form.Item
            name="_preset"
            label={t("cronJobs.form.preset")}
            rules={[
              { required: true, message: t("cronJobs.pleaseSelectPreset") },
            ]}
            tooltip={t("cronJobs.form.presetTooltip")}
          >
            <Select options={presetOptions} />
          </Form.Item>
        ) : (
          <>
            <Form.Item
              label={t("cronJobs.form.cronQuickPick")}
              tooltip={t("cronJobs.form.cronQuickPickTooltip")}
            >
              <Select
                allowClear
                placeholder={t("cronJobs.form.cronQuickPickPlaceholder")}
                options={presetOptions}
                onChange={(value) => {
                  if (!value) return;
                  const cron = presetToCron(value);
                  if (cron) {
                    form.setFieldValue(["schedule", "cron"], cron);
                  }
                }}
              />
            </Form.Item>
            <Form.Item
              name={["schedule", "cron"]}
              label={t("cronJobs.form.cron")}
              rules={[
                { required: true, message: t("cronJobs.pleaseInputCron") },
              ]}
              tooltip={t("cronJobs.form.cronTooltip")}
              extra={
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {t("cronJobs.form.cronExamples")}
                </Text>
              }
            >
              <Input
                placeholder="0 9 * * *"
                style={{ fontFamily: "monospace" }}
              />
            </Form.Item>
          </>
        )}

        <Form.Item
          name={["schedule", "timezone"]}
          label={t("cronJobs.form.timezone")}
          tooltip={t("cronJobs.form.timezoneTooltip")}
        >
          <Input readOnly disabled />
        </Form.Item>

        <SectionHeader
          title={t("cronJobs.form.sectionTask")}
          description={t("cronJobs.form.sectionTaskDesc")}
        />

        <Form.Item
          name="task_type"
          label={t("cronJobs.form.taskType")}
          tooltip={t("cronJobs.form.taskTypeTooltip")}
          rules={[
            { required: true, message: t("cronJobs.pleaseSelectTaskType") },
          ]}
        >
          <Select>
            <Select.Option value="agent">
              {t("cronJobs.form.taskTypeAgent")}
            </Select.Option>
            <Select.Option value="text">
              {t("cronJobs.form.taskTypeText")}
            </Select.Option>
          </Select>
        </Form.Item>

        <Form.Item
          name="prompt"
          label={t("cronJobs.form.agentPrompt")}
          rules={[
            { required: true, message: t("cronJobs.form.agentPromptRequired") },
            {
              max: CRON_PROMPT_MAX_LEN,
              message: t("cronJobs.form.agentPromptTooLong", {
                max: CRON_PROMPT_MAX_LEN,
              }),
            },
          ]}
          tooltip={t("cronJobs.form.agentPromptTooltip")}
        >
          <Input.TextArea
            rows={4}
            maxLength={CRON_PROMPT_MAX_LEN}
            showCount
            placeholder={t("cronJobs.form.agentPromptPlaceholder")}
          />
        </Form.Item>

        <Form.Item
          name="model"
          label={t("cronJobs.form.model")}
          tooltip={t("cronJobs.form.modelTooltip")}
          initialValue={MODEL_AUTO_VALUE}
        >
          <Select
            showSearch
            loading={modelsLoading}
            options={modelOptions}
            filterOption={(input, option) =>
              (option?.label?.toString() || "")
                .toLowerCase()
                .includes(input.toLowerCase())
            }
          />
        </Form.Item>

        <Form.Item
          name="mcp_servers"
          label={t("cronJobs.form.connectors")}
          tooltip={t("cronJobs.form.connectorsTooltip")}
          extra={
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("cronJobs.form.connectorsHint")}
            </Text>
          }
        >
          <Select
            mode="multiple"
            allowClear
            showSearch
            loading={connectorsLoading}
            placeholder={t("cronJobs.form.connectorsPlaceholder")}
            options={connectorOptions}
            optionFilterProp="label"
          />
        </Form.Item>

        <Form.Item
          name="fresh_thread"
          label={t("cronJobs.form.freshThread")}
          valuePropName="checked"
          tooltip={t("cronJobs.form.freshThreadTooltip")}
        >
          <Switch
            onChange={(checked) => {
              if (checked) {
                form.setFieldValue("session_key", undefined);
              }
            }}
          />
        </Form.Item>

        {!freshThread && (
          <>
            <SectionHeader
              title={t("cronJobs.form.sectionRouting")}
              description={t("cronJobs.form.sectionRoutingDesc")}
            />

            <Form.Item
              name="session_key"
              label={t("cronJobs.form.sessionKey")}
              tooltip={t("cronJobs.form.sessionKeyTooltip")}
              extra={
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {t("cronJobs.form.sessionKeyDefault")}
                </Text>
              }
            >
              <Select
                allowClear
                showSearch
                loading={sessionsLoading}
                placeholder={t("cronJobs.form.sessionKeyPlaceholder")}
                options={sessionOptions}
                filterOption={(input, option) =>
                  (option?.label?.toString() || "")
                    .toLowerCase()
                    .includes(input.toLowerCase())
                }
              />
            </Form.Item>
          </>
        )}

        <Form.Item>
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 8,
              marginTop: 16,
            }}
          >
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            <Button type="primary" htmlType="submit">
              {t("common.save")}
            </Button>
          </div>
        </Form.Item>
      </Form>
    </Drawer>
  );
}
