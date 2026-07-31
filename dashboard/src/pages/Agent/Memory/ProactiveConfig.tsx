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
} from "antd";
import { message } from "@/utils/antdMessage";

import { useTranslation } from "react-i18next";
import dayjs from "dayjs";
import api from "../../../api";
import type { ProactiveCareConfig } from "../../../api/types";
import styles from "./ProactiveConfig.module.less";

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

  useEffect(() => {
    fetchConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const fetchConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const config = await api.getProactiveCareConfig(agentId);
      setEnabled(config.enabled);

      form.setFieldsValue({
        enabled: config.enabled,
        active_hours_start: dayjs(
          config.active_hours_start || "09:00",
          "HH:mm",
        ),
        active_hours_end: dayjs(config.active_hours_end || "22:00", "HH:mm"),
        min_interval_hours: config.min_interval_hours ?? 5,
        max_interval_hours: config.max_interval_hours ?? 24,
      });
    } catch (err) {
      const errMsg =
        err instanceof Error
          ? err.message
          : t("proactiveConfig.loadFailed", "加载配置失败");
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();

      const startStr: string = dayjs(values.active_hours_start).format("HH:mm");
      const endStr: string = dayjs(values.active_hours_end).format("HH:mm");

      // Validate the time range.
      if (startStr >= endStr) {
        message.error(
          t(
            "proactiveConfig.timeRangeError",
            "关心时段的开始时间必须早于结束时间",
          ),
        );
        return;
      }

      const payload: ProactiveCareConfig = {
        enabled: values.enabled,
        active_hours_start: startStr,
        active_hours_end: endStr,
        min_interval_hours: values.min_interval_hours,
        max_interval_hours: values.max_interval_hours,
        episode_filter: null,
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
    fetchConfig();
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
        <Button size="small" onClick={fetchConfig} style={{ marginTop: 12 }}>
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
              "让 Octop 在合适的时机，主动向你发送一句关心",
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
