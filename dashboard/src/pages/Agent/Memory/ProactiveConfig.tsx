import { useState, useEffect } from "react";
import {
  Form,
  InputNumber,
  Button,
  Card,
  Switch,
  TimePicker,
  Alert,
  Divider,
  Spin,
  Select,
} from "antd";
import { message } from "@/utils/antdMessage";

import { useTranslation } from "react-i18next";
import dayjs from "dayjs";
import customParseFormat from "dayjs/plugin/customParseFormat";
import api from "../../../api";
import { providerApi } from "../../../api/modules/provider";
import {
  buildModelSelectOptions,
  defaultModelFromForm,
  defaultModelToForm,
  modelOptionValue,
} from "../../../utils/modelOptions";
import type { ProactiveCareConfig, ResolvedModel } from "../../../api/types";
import styles from "./ProactiveConfig.module.less";

dayjs.extend(customParseFormat);

interface Props {
  agentId: string;
  /** Switch to the episodes tab when the "view episodes" action is clicked. */
  onSwitchToEpisodes?: () => void;
}

export default function ProactiveConfig({
  agentId,
  onSwitchToEpisodes,
}: Readonly<Props>) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);

  const [models, setModels] = useState<ResolvedModel[] | null>(null);
  const [defaultRef, setDefaultRef] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const selectedRef = Form.useWatch("model_ref", form) || defaultRef;
  const reasoning = models?.find(
    (model) => modelOptionValue(model) === selectedRef,
  )?.reasoning_config;

  const loadFailed = t("proactiveConfig.loadFailed", "加载配置失败");
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      api.getProactiveCareConfig(agentId),
      providerApi.listResolvedModels(agentId).catch(() => null),
    ])
      .then(([config, choices]) => {
        if (cancelled) return;
        setModels(choices);
        setDefaultRef(config.default_model_ref ?? null);
        setEnabled(config.enabled);
        form.setFieldsValue({
          ...config,
          active_hours_start: dayjs(
            config.active_hours_start || "09:00",
            "HH:mm",
          ),
          active_hours_end: dayjs(config.active_hours_end || "22:00", "HH:mm"),
          model_ref: defaultModelToForm(config.model_ref),
          reasoning_effort: config.reasoning_effort ?? "auto",
          generation_timeout_seconds: config.generation_timeout_seconds ?? 30,
        });
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : loadFailed);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, form, reload, loadFailed]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();

      const startStr: string = dayjs(values.active_hours_start).format("HH:mm");
      const endStr: string = dayjs(values.active_hours_end).format("HH:mm");

      // An earlier end is a window that crosses midnight. Only an empty window is invalid.
      if (startStr === endStr) {
        message.error(
          t("proactiveConfig.timeRangeError", "关心时段的开始和结束不能相同"),
        );
        return;
      }

      const payload: ProactiveCareConfig = {
        enabled: values.enabled,
        active_hours_start: startStr,
        active_hours_end: endStr,
        min_interval_hours: values.min_interval_hours,
        max_interval_hours: values.max_interval_hours,
        model_ref: defaultModelFromForm(values.model_ref),
        reasoning_effort: values.reasoning_effort,
        generation_timeout_seconds: values.generation_timeout_seconds,
      };

      setSaving(true);
      await api.updateProactiveCareConfig(agentId, payload);
      message.success(t("proactiveConfig.saveSuccess", "保存成功"));
    } catch (err) {
      if (err instanceof Error && "errorFields" in err) {
        // Form validation failed; antd already shows errors, so do not add another toast.
        return;
      }
      const errMsg =
        err instanceof Error
          ? err.message
          : t("proactiveConfig.saveFailed", "保存失败");
      message.error(errMsg);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setReload((count) => count + 1);
  };

  if (loading) {
    return (
      <div className={styles.centerState}>
        <Spin />
        <span className={styles.stateText}>
          {t("common.loading", "加载中…")}
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.centerState}>
        <span className={styles.stateTextError}>{error}</span>
        <Button size="small" onClick={handleReset} style={{ marginTop: 12 }}>
          {t("environments.retry", "重试")}
        </Button>
      </div>
    );
  }

  return (
    <div className={styles.proactiveConfig}>
      {/* ── Header ── */}
      <div className={styles.configHeader}>
        <div>
          <h3 className={styles.configTitle}>
            {t("proactiveConfig.title", "主动关心")}
          </h3>
          <p className={styles.configDesc}>
            {t(
              "proactiveConfig.description",
              "等对话闲下来、并且处在关心时段里，才会主动说一句",
            )}
          </p>
        </div>
      </div>

      {/* ── Episode source explanation banner ── */}
      <Alert
        type="info"
        showIcon
        message={
          <span>
            {t(
              "proactiveConfig.episodeBannerText",
              "Octop 会从你的情绪日记中挑选合适的时机，主动发来一句关心。你可以在「情绪日记」中查看哪些记录会被参考。",
            )}
            {onSwitchToEpisodes && (
              <>
                {" "}
                <button
                  type="button"
                  onClick={onSwitchToEpisodes}
                  style={{
                    background: "none",
                    border: "none",
                    padding: 0,
                    color: "inherit",
                    textDecoration: "underline",
                    cursor: "pointer",
                    fontWeight: 500,
                    fontSize: "inherit",
                  }}
                >
                  {t("proactiveConfig.viewEpisodes", "去看情绪日记 →")}
                </button>
              </>
            )}
          </span>
        }
      />

      <Card className={styles.configCard}>
        <Form form={form} layout="vertical" className={styles.form}>
          {/* ── Enable switch ── */}
          <Form.Item
            label={t("proactiveConfig.enabled", "开启主动关心")}
            name="enabled"
            valuePropName="checked"
            className={styles.switchItem}
          >
            <Switch onChange={(checked) => setEnabled(checked)} />
          </Form.Item>

          <Divider style={{ margin: "8px 0" }} />

          {/* ── Active hours ── */}
          <div className={styles.timeRangeRow}>
            <Form.Item
              label={t("proactiveConfig.activeHoursStart", "关心时段 · 开始")}
              name="active_hours_start"
              className={styles.timeRangeItem}
              rules={[
                {
                  required: true,
                  message: t(
                    "proactiveConfig.activeHoursStartRequired",
                    "请选择开始时间",
                  ),
                },
              ]}
            >
              <TimePicker
                format="HH:mm"
                style={{ width: "100%" }}
                needConfirm={false}
                disabled={!enabled}
              />
            </Form.Item>
            <Form.Item
              label={t("proactiveConfig.activeHoursEnd", "关心时段 · 结束")}
              name="active_hours_end"
              className={styles.timeRangeItem}
              rules={[
                {
                  required: true,
                  message: t(
                    "proactiveConfig.activeHoursEndRequired",
                    "请选择结束时间",
                  ),
                },
              ]}
            >
              <TimePicker
                format="HH:mm"
                style={{ width: "100%" }}
                needConfirm={false}
                disabled={!enabled}
              />
            </Form.Item>
          </div>

          {/* ── Push interval ── */}
          <div className={styles.timeRangeRow}>
            <Form.Item
              label={t("proactiveConfig.minIntervalHours", "最短间隔（小时）")}
              name="min_interval_hours"
              className={styles.timeRangeItem}
              rules={[
                {
                  required: true,
                  message: t(
                    "proactiveConfig.minIntervalRequired",
                    "请输入最小间隔",
                  ),
                },
                {
                  type: "number",
                  min: 1,
                  message: t(
                    "proactiveConfig.minIntervalMin",
                    "最小间隔不能小于 1 小时",
                  ),
                },
                {
                  validator: (_, value) => {
                    const max = form.getFieldValue("max_interval_hours");
                    if (value != null && max != null && value > max) {
                      return Promise.reject(
                        t(
                          "proactiveConfig.intervalOrderError",
                          "最短间隔不能大于最长间隔",
                        ),
                      );
                    }
                    return Promise.resolve();
                  },
                },
              ]}
            >
              <InputNumber
                min={1}
                precision={0}
                style={{ width: "100%" }}
                disabled={!enabled}
                onChange={() => {
                  // Revalidate max_interval_hours.
                  form.validateFields(["max_interval_hours"]);
                }}
              />
            </Form.Item>
            <Form.Item
              label={t("proactiveConfig.maxIntervalHours", "最长间隔（小时）")}
              name="max_interval_hours"
              className={styles.timeRangeItem}
              rules={[
                {
                  required: true,
                  message: t(
                    "proactiveConfig.maxIntervalRequired",
                    "请输入最大间隔",
                  ),
                },
                {
                  validator: (_, value) => {
                    const min = form.getFieldValue("min_interval_hours");
                    if (value != null && min != null && value < min) {
                      return Promise.reject(
                        t(
                          "proactiveConfig.intervalOrderError",
                          "最长间隔不能小于最短间隔",
                        ),
                      );
                    }
                    return Promise.resolve();
                  },
                },
              ]}
            >
              <InputNumber
                min={1}
                precision={0}
                style={{ width: "100%" }}
                disabled={!enabled}
                onChange={() => {
                  form.validateFields(["min_interval_hours"]);
                }}
              />
            </Form.Item>
          </div>
          <Form.Item
            name="model_ref"
            label={t("proactiveConfig.generationModel")}
            extra={
              models === null
                ? t("proactiveConfig.modelsUnavailable")
                : undefined
            }
          >
            <Select
              showSearch
              optionFilterProp="label"
              disabled={!enabled || models === null}
              options={buildModelSelectOptions(
                models ?? [],
                t("proactiveConfig.followAgent"),
              )}
              onChange={() => form.setFieldValue("reasoning_effort", "auto")}
            />
          </Form.Item>
          <Form.Item
            name="reasoning_effort"
            label={t("proactiveConfig.reasoningEffort")}
          >
            <Select
              disabled={!enabled || models === null}
              options={[
                { value: "auto", label: t("proactiveConfig.modelDefault") },
                ...(reasoning?.toggle
                  ? [
                      {
                        value: "disabled",
                        label: t("proactiveConfig.disableThinking"),
                      },
                    ]
                  : []),
                ...(reasoning?.efforts ?? []).map((value) => ({
                  value,
                  label: value,
                })),
              ]}
            />
          </Form.Item>
          <Form.Item
            name="generation_timeout_seconds"
            label={t("proactiveConfig.generationTimeout")}
            extra={t("proactiveConfig.timeoutHint")}
            rules={[
              {
                required: true,
                type: "integer",
                min: 1,
                max: 3600,
                message: t("proactiveConfig.timeoutRange"),
              },
            ]}
          >
            <InputNumber min={1} max={3600} precision={0} disabled={!enabled} />
          </Form.Item>
        </Form>

        <div className={styles.actions}>
          <Button type="primary" loading={saving} onClick={handleSave}>
            {t("common.save", "保存")}
          </Button>
          <Button onClick={handleReset} disabled={saving}>
            {t("common.reset", "重置")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
