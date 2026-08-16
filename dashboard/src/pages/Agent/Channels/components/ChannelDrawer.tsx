import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Segmented,
  Select,
  Spin,
  Switch,
} from "antd";
import { Activity } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { FormInstance } from "antd";
import type { Rule } from "antd/es/form";
import { QRCodeSVG } from "qrcode.react";
import {
  CHANNEL_FIELDS,
  CHANNEL_ICONS,
  CHANNEL_KEYS,
  CHANNEL_LABELS,
  CHANNEL_LABEL_KEYS,
  CHANNEL_URLS,
  DEFAULT_CHANNEL_DISPLAY_CONFIG,
  DEFAULT_QQ_GROUP_CONTEXT_CONFIG,
  normalizeChannelFieldValue,
  normalizeQqGroupContextConfig,
  type ChannelField,
  type ChannelKey,
  type QqGroupActivation,
  type QqGroupContextConfig,
  type QqGroupVisibility,
} from "./constants";
import type { ChannelRow } from "../useChannels";
import styles from "../index.module.less";
import { channelApi } from "../../../../api/modules/channel";
import {
  clearFormDraft,
  loadFormDraft,
  saveFormDraft,
} from "../../../../utils/formDraft";

/** QR auto-save keys (module-wide) so Strict Mode remounts don't double-submit. */
const QR_AUTOSAVE_TTL_MS = 10 * 60 * 1000;
const qrAutoSavedAt = new Map<string, number>();

function hasRecentQrAutoSave(key: string): boolean {
  const at = qrAutoSavedAt.get(key);
  if (at == null) return false;
  if (Date.now() - at > QR_AUTOSAVE_TTL_MS) {
    qrAutoSavedAt.delete(key);
    return false;
  }
  return true;
}

function markQrAutoSave(key: string) {
  qrAutoSavedAt.set(key, Date.now());
  if (qrAutoSavedAt.size <= 64) return;
  const cutoff = Date.now() - QR_AUTOSAVE_TTL_MS;
  for (const [k, t] of qrAutoSavedAt) {
    if (t < cutoff) qrAutoSavedAt.delete(k);
  }
}

function clearQrAutoSave(key: string) {
  qrAutoSavedAt.delete(key);
}

export interface ChannelFormValues {
  kind: ChannelKey;
  name?: string;
  enabled?: boolean;
  response_mode?: "invoke" | "stream";
  show_thinking?: boolean;
  show_tool_hints?: boolean;
  group_context?: QqGroupContextConfig;
  [k: string]: string | boolean | QqGroupContextConfig | undefined;
  __raw_config?: string;
}

// Channels that support QR quick-config
const QUICK_CONFIG_CHANNELS: ChannelKey[] = [
  "qq",
  "wecom",
  "weixin",
  "feishu",
  "yuanbao",
];

const YUANBAO_DEFAULT_API_DOMAIN = "https://bot.yuanbao.tencent.com";
const YUANBAO_DEFAULT_WS_URL =
  "wss://bot-wss.yuanbao.tencent.com/wss/connection";

// QR State Machine
type QrPhase =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "qq_ready"; qrcodeUrl: string; qrcodeToken: string }
  | {
      phase: "qq_success";
      appId: string;
      secret: string;
    }
  | { phase: "wecom_ready"; authUrl: string; scode: string }
  | { phase: "wecom_success"; botId: string; secret: string }
  | { phase: "weixin_ready"; qrcodeUrl: string; qrcodeToken: string }
  | {
      phase: "weixin_success";
      accountId: string;
      token: string;
      baseUrl: string;
    }
  | { phase: "feishu_creating"; message: string }
  | { phase: "feishu_qr"; qrToken: string }
  | { phase: "feishu_progress"; message: string }
  | {
      phase: "feishu_done";
      appId: string;
      appSecret: string;
      botName?: string;
      manageUrl?: string;
    }
  | { phase: "yuanbao_creating"; message: string }
  | { phase: "yuanbao_scan"; scanCode: string; scanUrl?: string }
  | { phase: "yuanbao_progress"; message: string }
  | { phase: "yuanbao_done"; appKey: string; appSecret: string }
  | { phase: "error"; reason: string };

interface ChannelDrawerProps {
  open: boolean;
  editing: ChannelRow | null;
  loadingConfig: boolean;
  initialValues: ChannelFormValues | undefined;
  form: FormInstance<ChannelFormValues>;
  saving: boolean;
  onDelete?: () => void;
  deleting?: boolean;
  onClose: () => void;
  onSubmit: (
    kind: ChannelKey,
    name: string,
    config: Record<string, unknown>,
    enabled: boolean,
  ) => Promise<boolean>;
  onTest?: () => void;
  testing?: boolean;
  agentId: string;
}

function FormItemForField({ field }: { field: ChannelField }) {
  const Input1 =
    field.type === "password"
      ? Input.Password
      : field.type === "textarea" || field.type === "json"
      ? Input.TextArea
      : Input;
  const rules: Rule[] = field.required
    ? [{ required: true, message: `${field.label} 必填` }]
    : [];
  if (field.type === "json") {
    rules.push({
      validator: async (_: unknown, value: unknown) => {
        if (!value) return;
        try {
          normalizeChannelFieldValue(field.name, value);
        } catch {
          throw new Error(`${field.label} 必须是 JSON 对象`);
        }
      },
    });
  }
  return (
    <Form.Item name={field.name} label={field.label} rules={rules}>
      <Input1
        placeholder={field.placeholder}
        {...(field.type === "textarea" || field.type === "json"
          ? { rows: 5 }
          : {})}
      />
    </Form.Item>
  );
}

interface PolicyTagOption<T extends string> {
  label: string;
  value: T;
  disabled?: boolean;
}

function PolicyTagGroup<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value?: T;
  options: PolicyTagOption<T>[];
  onChange?: (value: T) => void;
  ariaLabel: string;
}) {
  return (
    <div
      className={styles.qqGroupPolicyTags}
      role="radiogroup"
      aria-label={ariaLabel}
    >
      {options.map((option) => {
        const checked = value === option.value;
        return (
          <button
            key={option.value}
            className={`${styles.qqGroupPolicyTag} ${
              checked ? styles.qqGroupPolicyTagChecked : ""
            } ${option.disabled ? styles.qqGroupPolicyTagDisabled : ""}`}
            type="button"
            role="radio"
            aria-checked={checked}
            disabled={option.disabled}
            tabIndex={option.disabled ? -1 : 0}
            onClick={() => {
              if (!checked && !option.disabled) {
                onChange?.(option.value);
              }
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function QqGroupContextPolicyFields({
  form,
}: {
  form: FormInstance<ChannelFormValues>;
}) {
  const { t } = useTranslation();
  useEffect(() => {
    form.setFieldValue(
      "group_context",
      normalizeQqGroupContextConfig(form.getFieldValue("group_context")),
    );
  }, [form]);
  const watchedEnabled = Form.useWatch(["group_context", "enabled"], form);
  const watchedVisibility = Form.useWatch(
    ["group_context", "visibility"],
    form,
  );
  const watchedActivation = Form.useWatch(
    ["group_context", "activation"],
    form,
  );
  const policy = normalizeQqGroupContextConfig(
    form.getFieldValue("group_context"),
  );
  const enabled =
    typeof watchedEnabled === "boolean" ? watchedEnabled : policy.enabled;
  const visibility = (watchedVisibility ??
    policy.visibility) as QqGroupVisibility;
  const activation = (watchedActivation ??
    policy.activation) as QqGroupActivation;

  const updatePolicy = (patch: Partial<QqGroupContextConfig>) => {
    form.setFieldValue("group_context", {
      ...normalizeQqGroupContextConfig(form.getFieldValue("group_context")),
      ...patch,
    });
  };

  const handleVisibilityChange = (value: string | number) => {
    const nextVisibility = value as QqGroupVisibility;
    updatePolicy({
      visibility: nextVisibility,
      activation: nextVisibility === "all" ? activation : "mention",
      history: nextVisibility === "mention_only" ? "none" : "recent",
    });
  };

  return (
    <div className={styles.qqGroupPolicy}>
      <div className={styles.qqGroupPolicyHeader}>
        <div>
          <div className={styles.qqGroupPolicyTitle}>
            {t("channels.qqGroupPolicyTitle")}
          </div>
          <div className={styles.qqGroupPolicyDescription}>
            {t("channels.qqGroupPolicyDescription")}
          </div>
        </div>
        <Form.Item
          name={["group_context", "enabled"]}
          valuePropName="checked"
          noStyle
        >
          <Switch />
        </Form.Item>
      </div>

      {enabled && (
        <>
          <Form.Item
            name={["group_context", "visibility"]}
            label={t("channels.qqGroupVisibility")}
          >
            <PolicyTagGroup<QqGroupVisibility>
              ariaLabel={t("channels.qqGroupVisibility")}
              onChange={handleVisibilityChange}
              options={[
                {
                  label: t("channels.qqGroupVisibilityAuto"),
                  value: "auto",
                },
                {
                  label: t("channels.qqGroupVisibilityMentionOnly"),
                  value: "mention_only",
                },
                {
                  label: t("channels.qqGroupVisibilityMentionRecent"),
                  value: "mention_recent",
                },
                {
                  label: t("channels.qqGroupVisibilityAll"),
                  value: "all",
                },
              ]}
            />
          </Form.Item>

          <div className={styles.qqGroupPolicyGrid}>
            <Form.Item
              name={["group_context", "activation"]}
              label={t("channels.qqGroupActivation")}
            >
              <PolicyTagGroup<QqGroupActivation>
                ariaLabel={t("channels.qqGroupActivation")}
                options={[
                  {
                    label: t("channels.qqGroupActivationMention"),
                    value: "mention",
                  },
                  {
                    label: t("channels.qqGroupActivationAlways"),
                    value: "always",
                    disabled: visibility !== "all",
                  },
                ]}
              />
            </Form.Item>
            <Form.Item
              name={["group_context", "history_limit"]}
              label={t("channels.qqGroupHistoryLimit")}
              rules={[{ type: "number", min: 0, max: 50 }]}
            >
              <InputNumber
                min={0}
                max={50}
                precision={0}
                disabled={visibility === "mention_only"}
                style={{ width: "100%" }}
              />
            </Form.Item>
          </div>

          <Form.Item
            name={["group_context", "clear_after_reply"]}
            label={t("channels.qqGroupClearAfterReply")}
            tooltip={t("channels.qqGroupClearAfterReplyDesc")}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          {activation === "always" && (
            <Alert
              showIcon
              type="warning"
              message={t("channels.qqGroupAlwaysWarning")}
            />
          )}
        </>
      )}
    </div>
  );
}

function DisplaySettingsFields() {
  const { t } = useTranslation();
  const responseMode =
    Form.useWatch("response_mode") ??
    DEFAULT_CHANNEL_DISPLAY_CONFIG.response_mode;
  return (
    <div className={styles.displaySettings}>
      <div className={styles.displaySettingsTitle}>
        {t("channels.channelSettings")}
      </div>
      <Form.Item
        name="enabled"
        label={t("channels.enableChannel")}
        tooltip={t("channels.enableChannelDesc")}
        valuePropName="checked"
      >
        <Switch />
      </Form.Item>
      <Form.Item
        name="response_mode"
        label={t("channels.responseMode")}
        tooltip={t("channels.responseModeDesc")}
      >
        <Segmented
          options={[
            {
              label: t("channels.responseModeInvoke"),
              value: "invoke",
            },
            {
              label: t("channels.responseModeStream"),
              value: "stream",
            },
          ]}
        />
      </Form.Item>
      <Form.Item
        name="show_thinking"
        label={t("channels.showThinking")}
        tooltip={t("channels.showThinkingDesc")}
        valuePropName="checked"
      >
        <Switch disabled={responseMode === "invoke"} />
      </Form.Item>
      <Form.Item
        name="show_tool_hints"
        label={t("channels.showToolHints")}
        tooltip={t("channels.showToolHintsDesc")}
        valuePropName="checked"
      >
        <Switch disabled={responseMode === "invoke"} />
      </Form.Item>
    </div>
  );
}

export function ChannelDrawer({
  open,
  editing,
  loadingConfig,
  initialValues,
  form,
  saving,
  onDelete,
  deleting,
  onClose,
  onSubmit,
  onTest,
  testing,
  agentId,
}: ChannelDrawerProps) {
  const { t } = useTranslation();
  const isEdit = editing !== null;
  const [selectedKind, setSelectedKind] = useState<ChannelKey>(
    initialValues?.kind ?? "feishu",
  );
  const [configMode, setConfigMode] = useState<"quick" | "manual">("quick");
  const [qrState, setQrState] = useState<QrPhase>({ phase: "idle" });
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoSaveTriggeredRef = useRef(false);
  const [autoSaveFailed, setAutoSaveFailed] = useState(false);

  const supportsQuickConfig = QUICK_CONFIG_CHANNELS.includes(selectedKind);
  // weixin has no manual form — always quick-only
  const isQuickOnly = selectedKind === "weixin";
  const draftScope = editing
    ? `channel:${editing.id}`
    : selectedKind
    ? `channel:new:${selectedKind}`
    : "";
  const restoringDraftRef = useRef(false);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const resetQr = useCallback(() => {
    stopPolling();
    autoSaveTriggeredRef.current = false;
    setAutoSaveFailed(false);
    setQrState({ phase: "idle" });
  }, [stopPolling]);

  useEffect(() => {
    if (!open) {
      resetQr();
      setConfigMode("quick");
    }
  }, [open, resetQr]);

  useEffect(() => {
    resetQr();
  }, [selectedKind, resetQr]);

  useEffect(() => {
    if (open && initialValues?.kind) {
      setSelectedKind(initialValues.kind);
    }
  }, [open, initialValues?.kind]);

  // Restore session draft after server/default values are applied.
  useEffect(() => {
    if (!open || loadingConfig || !draftScope) return;
    const draft = loadFormDraft<ChannelFormValues>(draftScope);
    if (!draft) return;
    restoringDraftRef.current = true;
    form.setFieldsValue(draft);
    if (draft.kind) setSelectedKind(draft.kind);
    restoringDraftRef.current = false;
  }, [open, loadingConfig, draftScope, form]);

  // ── QQ Bot Flow ────────────────────────────────────────────────────────
  const startQqQr = useCallback(async () => {
    setQrState({ phase: "loading" });
    try {
      const res = await channelApi.qqQrcodeGenerate(agentId);
      setQrState({
        phase: "qq_ready",
        qrcodeUrl: res.qrcode_url,
        qrcodeToken: res.qrcode_token,
      });
      const timer = setInterval(async () => {
        try {
          const poll = await channelApi.qqQrcodePoll(agentId, res.qrcode_token);
          if (poll.status === "success" && poll.app_id && poll.secret) {
            stopPolling();
            setQrState({
              phase: "qq_success",
              appId: poll.app_id,
              secret: poll.secret,
            });
          } else if (poll.status === "error" || poll.status === "expired") {
            stopPolling();
            setQrState({
              phase: "error",
              reason: poll.message ?? t("channels.qqQrFailed"),
            });
          }
        } catch {
          // network error — keep polling
        }
      }, 2000);
      pollTimerRef.current = timer;
    } catch (e: unknown) {
      setQrState({
        phase: "error",
        reason: e instanceof Error ? e.message : String(e),
      });
    }
  }, [agentId, stopPolling, t]);

  // ── WeCom Flow ─────────────────────────────────────────────────────────
  const startWecomQr = useCallback(async () => {
    setQrState({ phase: "loading" });
    try {
      const res = await channelApi.wecomQrcodeGenerate(agentId);
      setQrState({
        phase: "wecom_ready",
        authUrl: res.auth_url,
        scode: res.scode,
      });
      const timer = setInterval(async () => {
        try {
          const poll = await channelApi.wecomQrcodePoll(agentId, res.scode);
          if (poll.status === "success" && poll.bot_id && poll.secret) {
            stopPolling();
            setQrState({
              phase: "wecom_success",
              botId: poll.bot_id,
              secret: poll.secret,
            });
          } else if (poll.status === "error") {
            stopPolling();
            setQrState({ phase: "error", reason: poll.reason ?? "扫码失败" });
          }
        } catch {
          // network error — keep polling
        }
      }, 2000);
      pollTimerRef.current = timer;
    } catch (e: unknown) {
      setQrState({
        phase: "error",
        reason: e instanceof Error ? e.message : String(e),
      });
    }
  }, [agentId, stopPolling]);

  // ── WeChat Flow ─────────────────────────────────────────────────────────
  const startWeixinQr = useCallback(async () => {
    setQrState({ phase: "loading" });
    try {
      const res = await channelApi.weixinQrcodeGenerate(agentId);
      setQrState({
        phase: "weixin_ready",
        qrcodeUrl: res.qrcode_url,
        qrcodeToken: res.qrcode_token,
      });
      const timer = setInterval(async () => {
        try {
          const poll = await channelApi.weixinQrcodePoll(
            agentId,
            res.qrcode_token,
          );
          if (poll.status === "success" && poll.token) {
            stopPolling();
            setQrState({
              phase: "weixin_success",
              accountId: poll.account_id ?? "",
              token: poll.token,
              baseUrl: poll.base_url ?? "",
            });
          } else if (poll.status === "error") {
            stopPolling();
            setQrState({ phase: "error", reason: poll.message ?? "扫码失败" });
          }
        } catch {
          // keep polling
        }
      }, 3000);
      pollTimerRef.current = timer;
    } catch (e: unknown) {
      setQrState({
        phase: "error",
        reason: e instanceof Error ? e.message : String(e),
      });
    }
  }, [agentId, stopPolling]);

  // ── Feishu Flow ─────────────────────────────────────────────────────────
  const startFeishuCreator = useCallback(
    async (platform: "feishu" | "lark" = "feishu") => {
      setQrState({
        phase: "feishu_creating",
        message: "启动飞书机器人创建流程...",
      });
      try {
        await channelApi.feishuBotCreatorStart(agentId, { platform });
      } catch (e: unknown) {
        setQrState({
          phase: "error",
          reason: e instanceof Error ? e.message : String(e),
        });
        return;
      }
      const timer = setInterval(async () => {
        try {
          const poll = await channelApi.feishuBotCreatorPoll(agentId);
          let enteredProgress = false;
          for (const ev of poll.events) {
            if (
              ev.action === "progress" &&
              ev.message !== "Waiting for scan..."
            ) {
              enteredProgress = true;
              setQrState({ phase: "feishu_progress", message: ev.message });
            }
            if (
              ev.action === "log" &&
              ev.step === "login" &&
              (ev.message.includes("Scanned") || ev.level === "success")
            ) {
              enteredProgress = true;
              setQrState({
                phase: "feishu_progress",
                message: ev.message.includes("Scanned")
                  ? "已扫码，请在手机上确认登录"
                  : "登录成功，正在自动创建机器人，请稍候…",
              });
            }
          }
          if (poll.qr_token && !enteredProgress) {
            setQrState((prev) =>
              prev.phase === "feishu_progress"
                ? prev
                : { phase: "feishu_qr", qrToken: poll.qr_token! },
            );
          }
          if (poll.status === "finished" && poll.app_id && poll.app_secret) {
            stopPolling();
            const finishEvent = poll.events.find(
              (e) => e.action === "finish" && e.level === "success",
            );
            const data = (finishEvent?.data ?? {}) as Record<string, unknown>;
            setQrState({
              phase: "feishu_done",
              appId: poll.app_id,
              appSecret: poll.app_secret,
              botName: data.bot_name as string | undefined,
              manageUrl: data.manage_url as string | undefined,
            });
          } else if (poll.status === "failed") {
            stopPolling();
            const errEvent = poll.events.find(
              (e) => e.action === "finish" && e.level === "error",
            );
            setQrState({
              phase: "error",
              reason: errEvent?.message ?? "飞书机器人创建失败",
            });
          }
        } catch {
          // keep polling
        }
      }, 1500);
      pollTimerRef.current = timer;
    },
    [agentId, stopPolling],
  );

  // ── YuanBao Flow ────────────────────────────────────────────────────────
  const startYuanbaoCreator = useCallback(async () => {
    setQrState({
      phase: "yuanbao_creating",
      message: "启动元宝扫码绑定流程...",
    });
    try {
      await channelApi.yuanbaoBotCreatorStart(agentId, {});
    } catch (e: unknown) {
      setQrState({
        phase: "error",
        reason: e instanceof Error ? e.message : String(e),
      });
      return;
    }
    const timer = setInterval(async () => {
      try {
        const poll = await channelApi.yuanbaoBotCreatorPoll(agentId);
        if (poll.scan_code) {
          setQrState({
            phase: "yuanbao_scan",
            scanCode: poll.scan_code,
            scanUrl: poll.scan_url,
          });
        }
        const lastEvent = poll.events[poll.events.length - 1];
        if (lastEvent?.action === "progress") {
          setQrState((prev) =>
            prev.phase === "yuanbao_scan"
              ? prev
              : { phase: "yuanbao_progress", message: lastEvent.message },
          );
        }
        if (poll.status === "finished" && poll.app_key && poll.app_secret) {
          stopPolling();
          setQrState({
            phase: "yuanbao_done",
            appKey: poll.app_key,
            appSecret: poll.app_secret,
          });
        } else if (poll.status === "failed") {
          stopPolling();
          const errEvent = poll.events.find(
            (e) => e.action === "finish" && e.level === "error",
          );
          setQrState({
            phase: "error",
            reason: errEvent?.message ?? "元宝绑定失败",
          });
        }
      } catch {
        // keep polling
      }
    }, 2000);
    pollTimerRef.current = timer;
  }, [agentId, stopPolling]);

  // ── Form ────────────────────────────────────────────────────────────────
  const fields = CHANNEL_FIELDS[selectedKind];
  const hasSchema = !!fields && fields.length > 0;
  const labelKey = CHANNEL_LABEL_KEYS[selectedKind];
  const kindLabel = labelKey ? t(labelKey) : CHANNEL_LABELS[selectedKind];
  const introUrl = CHANNEL_URLS[selectedKind];

  const getDisplayConfig = useCallback((): Pick<
    ChannelFormValues,
    "response_mode" | "show_thinking" | "show_tool_hints"
  > => {
    const values = form.getFieldsValue([
      "response_mode",
      "show_thinking",
      "show_tool_hints",
    ]);
    return {
      response_mode:
        values.response_mode ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.response_mode,
      show_thinking:
        values.show_thinking ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.show_thinking,
      show_tool_hints:
        values.show_tool_hints ??
        DEFAULT_CHANNEL_DISPLAY_CONFIG.show_tool_hints,
    };
  }, [form]);

  const mergeDisplayConfig = useCallback(
    (config: Record<string, unknown>) => ({
      ...config,
      ...getDisplayConfig(),
    }),
    [getDisplayConfig],
  );

  const getQqGroupContextConfig = useCallback(
    () =>
      normalizeQqGroupContextConfig(
        form.getFieldValue("group_context") ?? DEFAULT_QQ_GROUP_CONTEXT_CONFIG,
      ),
    [form],
  );

  const submitChannel = useCallback(
    async (
      kind: ChannelKey,
      name: string,
      config: Record<string, unknown>,
      /** When set, overrides the form enabled switch (QR bind always enables). */
      enabledOverride?: boolean,
    ): Promise<boolean> => {
      const enabled =
        enabledOverride !== undefined
          ? enabledOverride
          : form.getFieldValue("enabled") ?? false;
      const ok = await onSubmit(kind, name, config, enabled);
      if (ok) clearFormDraft(draftScope);
      return ok;
    },
    [form, onSubmit, draftScope],
  );

  // Auto-save when QR quick-config completes — channel is usable immediately.
  useEffect(() => {
    if (isEdit || saving || autoSaveTriggeredRef.current) return;

    const s = qrState;
    let payload: {
      kind: ChannelKey;
      name: string;
      config: Record<string, unknown>;
    } | null = null;
    let dedupeKey: string | null = null;

    if (s.phase === "wecom_success") {
      dedupeKey = `wecom:${s.botId}:${s.secret}`;
      payload = {
        kind: "wecom",
        name: "wecom",
        config: mergeDisplayConfig({ bot_id: s.botId, secret: s.secret }),
      };
    } else if (s.phase === "qq_success") {
      dedupeKey = `qq:${s.appId}:${s.secret}`;
      payload = {
        kind: "qq",
        name: "qq",
        config: mergeDisplayConfig({
          app_id: s.appId,
          secret: s.secret,
          group_context: getQqGroupContextConfig(),
        }),
      };
    } else if (s.phase === "weixin_success") {
      dedupeKey = `weixin:${s.accountId}:${s.token}`;
      payload = {
        kind: "weixin",
        name: "weixin",
        config: mergeDisplayConfig({
          accounts: [
            {
              account_id: s.accountId || "weixin",
              token: s.token,
              base_url: s.baseUrl || "https://ilinkai.weixin.qq.com",
              bot_uin: s.accountId || "",
            },
          ],
          bot_uin: s.accountId || "",
          token: s.token,
          base_url: s.baseUrl || "https://ilinkai.weixin.qq.com",
        }),
      };
    } else if (s.phase === "feishu_done") {
      dedupeKey = `feishu:${s.appId}:${s.appSecret}`;
      payload = {
        kind: "feishu",
        name: "feishu",
        config: mergeDisplayConfig({
          app_id: s.appId,
          app_secret: s.appSecret,
        }),
      };
    } else if (s.phase === "yuanbao_done") {
      dedupeKey = `yuanbao:${s.appKey}:${s.appSecret}`;
      payload = {
        kind: "yuanbao",
        name: "yuanbao",
        config: mergeDisplayConfig({
          app_key: s.appKey,
          app_secret: s.appSecret,
          api_domain: YUANBAO_DEFAULT_API_DOMAIN,
          ws_url: YUANBAO_DEFAULT_WS_URL,
        }),
      };
    }

    if (!payload || !dedupeKey) return;
    if (hasRecentQrAutoSave(dedupeKey)) return;

    markQrAutoSave(dedupeKey);
    autoSaveTriggeredRef.current = true;
    setAutoSaveFailed(false);
    // QR bind success → enable channel so messages start flowing without a second toggle.
    void submitChannel(payload.kind, payload.name, payload.config, true).then(
      (ok) => {
        if (!ok) {
          autoSaveTriggeredRef.current = false;
          clearQrAutoSave(dedupeKey);
          setAutoSaveFailed(true);
        } else {
          form.setFieldValue("enabled", true);
        }
      },
    );
  }, [
    qrState,
    isEdit,
    saving,
    submitChannel,
    mergeDisplayConfig,
    getQqGroupContextConfig,
    form,
  ]);

  const showFooterSave =
    configMode === "manual" || isEdit || !supportsQuickConfig;

  const renderQrAutoSaveStatus = (retrySave?: () => Promise<boolean>) => {
    if (saving) {
      return (
        <div
          style={{
            marginTop: 12,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <Spin size="small" />
          <span style={{ color: "var(--fn-text-secondary)", fontSize: 13 }}>
            正在自动保存...
          </span>
        </div>
      );
    }
    if (autoSaveFailed && retrySave) {
      return (
        <Button
          type="primary"
          loading={saving}
          onClick={() => {
            autoSaveTriggeredRef.current = true;
            setAutoSaveFailed(false);
            void retrySave().then((ok) => {
              if (!ok) {
                autoSaveTriggeredRef.current = false;
                setAutoSaveFailed(true);
              }
            });
          }}
          style={{ marginTop: 12 }}
        >
          重试保存
        </Button>
      );
    }
    return null;
  };

  const handleClose = () => {
    stopPolling();
    if (selectedKind === "feishu")
      void channelApi.feishuBotCreatorStop(agentId).catch(() => {});
    if (selectedKind === "yuanbao")
      void channelApi.yuanbaoBotCreatorStop(agentId).catch(() => {});
    onClose();
  };

  const handleFinish = (values: ChannelFormValues) => {
    const {
      kind,
      __raw_config,
      response_mode,
      show_thinking,
      show_tool_hints,
      ...rest
    } = values;
    let config: Record<string, unknown> = {
      response_mode:
        response_mode ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.response_mode,
      show_thinking:
        show_thinking ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.show_thinking,
      show_tool_hints:
        show_tool_hints ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.show_tool_hints,
    };
    if (hasSchema) {
      for (const [k, v] of Object.entries(rest)) {
        if (k === "name" || v === undefined || v === null || v === "") continue;
        config[k] = normalizeChannelFieldValue(k, v);
      }
    } else if (__raw_config !== undefined) {
      const trimmed = __raw_config.trim();
      if (trimmed) {
        try {
          const parsed = JSON.parse(trimmed);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            config = parsed as Record<string, unknown>;
          }
        } catch {
          return;
        }
      }
    }
    config = {
      ...config,
      response_mode:
        response_mode ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.response_mode,
      show_thinking:
        show_thinking ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.show_thinking,
      show_tool_hints:
        show_tool_hints ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.show_tool_hints,
    };
    void (async () => {
      const ok = await onSubmit(kind, kind, config, values.enabled ?? false);
      if (ok) clearFormDraft(draftScope);
    })();
  };

  // ── QR Panels ───────────────────────────────────────────────────────────
  function renderQqPanel() {
    const s = qrState;
    if (s.phase === "loading")
      return (
        <div className={styles.qrPanel}>
          <Spin />
        </div>
      );
    if (s.phase === "qq_success") {
      const retrySave = () =>
        submitChannel(
          "qq",
          "qq",
          mergeDisplayConfig({
            app_id: s.appId,
            secret: s.secret,
            group_context: getQqGroupContextConfig(),
          }),
          true,
        );
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="success"
            message={t("channels.qqQrSuccess")}
            description={`App ID: ${s.appId}`}
            style={{ width: "100%", marginBottom: 12 }}
          />
          {renderQrAutoSaveStatus(retrySave)}
        </div>
      );
    }
    if (s.phase === "qq_ready") {
      return (
        <div className={styles.qrPanel}>
          <div className={styles.qrSteps}>
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>1</span>
              {t("channels.qqQrStep1")}
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>2</span>
              {t("channels.qqQrStep2")}
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>3</span>
              {t("channels.qqQrStep3")}
            </span>
          </div>
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={s.qrcodeUrl} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>{t("channels.qqQrScanHint")}</p>
          <Button size="small" onClick={resetQr} style={{ marginTop: 4 }}>
            {t("channels.qrRetry")}
          </Button>
        </div>
      );
    }
    if (s.phase === "error") {
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="error"
            message={s.reason}
            style={{ width: "100%", marginBottom: 12 }}
          />
          <Button onClick={() => void startQqQr()}>
            {t("channels.qrRetry")}
          </Button>
        </div>
      );
    }
    return (
      <div className={styles.quickConfigPanel}>
        <div className={styles.quickConfigSteps}>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>1</span>
            {t("channels.qqQrIntro1")}
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>2</span>
            {t("channels.qqQrIntro2")}
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>3</span>
            {t("channels.qqQrIntro3")}
          </div>
        </div>
        <Button
          type="primary"
          className={styles.quickConfigBtn}
          block
          onClick={() => void startQqQr()}
        >
          {t("channels.qqQrGenerate")}
        </Button>
      </div>
    );
  }

  function renderWecomPanel() {
    const s = qrState;
    if (s.phase === "loading")
      return (
        <div className={styles.qrPanel}>
          <Spin />
        </div>
      );
    if (s.phase === "wecom_success") {
      const retrySave = () =>
        submitChannel(
          "wecom",
          "wecom",
          mergeDisplayConfig({ bot_id: s.botId, secret: s.secret }),
          true,
        );
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="success"
            message="企业微信绑定成功"
            description={`Bot ID: ${s.botId}`}
            style={{ width: "100%", marginBottom: 12 }}
          />
          {renderQrAutoSaveStatus(retrySave)}
        </div>
      );
    }
    if (s.phase === "wecom_ready") {
      return (
        <div className={styles.qrPanel}>
          <div className={styles.qrSteps}>
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>1</span>打开企业微信
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>2</span>扫码注册 AI 机器人
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>3</span>确认绑定
            </span>
          </div>
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={s.authUrl} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>扫码后自动跳转下一步</p>
          <Button size="small" onClick={resetQr} style={{ marginTop: 4 }}>
            重新生成
          </Button>
        </div>
      );
    }
    if (s.phase === "error") {
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="error"
            message={s.reason}
            style={{ width: "100%", marginBottom: 12 }}
          />
          <Button onClick={() => void startWecomQr()}>重试</Button>
        </div>
      );
    }
    return (
      <div className={styles.quickConfigPanel}>
        <div className={styles.quickConfigSteps}>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>1</span>
            点击下方按钮，生成企业微信 AI 机器人注册二维码
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>2</span>用企业微信 App
            扫码，完成机器人注册
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>3</span>
            凭据自动填入并保存
          </div>
        </div>
        <Button
          type="primary"
          className={styles.quickConfigBtn}
          block
          onClick={() => void startWecomQr()}
        >
          生成扫码二维码
        </Button>
      </div>
    );
  }

  function renderWeixinPanel() {
    const s = qrState;
    if (s.phase === "loading")
      return (
        <div className={styles.qrPanel}>
          <Spin />
        </div>
      );
    if (s.phase === "weixin_success") {
      const weixinConfig = mergeDisplayConfig({
        accounts: [
          {
            account_id: s.accountId || "weixin",
            token: s.token,
            base_url: s.baseUrl || "https://ilinkai.weixin.qq.com",
            bot_uin: s.accountId || "",
          },
        ],
        bot_uin: s.accountId || "",
        token: s.token,
        base_url: s.baseUrl || "https://ilinkai.weixin.qq.com",
      });
      const retrySave = () =>
        submitChannel("weixin", "weixin", weixinConfig, true);
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="success"
            message="微信绑定成功"
            description={`账号 ID: ${s.accountId}`}
            style={{ width: "100%", marginBottom: 12 }}
          />
          {renderQrAutoSaveStatus(retrySave)}
        </div>
      );
    }
    if (s.phase === "weixin_ready") {
      return (
        <div className={styles.qrPanel}>
          <div className={styles.qrSteps}>
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>1</span>打开微信 App
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>2</span>扫码登录
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>3</span>手机确认
            </span>
          </div>
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={s.qrcodeUrl} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>使用微信扫码登录个人账号</p>
          <Button size="small" onClick={resetQr} style={{ marginTop: 4 }}>
            重新生成
          </Button>
        </div>
      );
    }
    if (s.phase === "error") {
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="error"
            message={s.reason}
            style={{ width: "100%", marginBottom: 12 }}
          />
          <Button onClick={() => void startWeixinQr()}>重试</Button>
        </div>
      );
    }
    return (
      <div className={styles.quickConfigPanel}>
        <div className={styles.quickConfigSteps}>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>1</span>
            点击按钮生成微信登录二维码
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>2</span>微信扫码并在手机确认登录
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>3</span>登录成功后自动保存配置
          </div>
        </div>
        <Button
          type="primary"
          className={styles.quickConfigBtn}
          block
          onClick={() => void startWeixinQr()}
        >
          生成微信扫码二维码
        </Button>
      </div>
    );
  }

  function renderFeishuPanel() {
    const s = qrState;
    if (s.phase === "feishu_creating" || s.phase === "feishu_progress") {
      return (
        <div className={styles.qrPanel}>
          <Spin />
          <p
            style={{
              marginTop: 12,
              color: "var(--fn-text-secondary)",
              fontSize: 13,
            }}
          >
            {s.message}
          </p>
        </div>
      );
    }
    if (s.phase === "feishu_qr") {
      const qrContent = JSON.stringify({ qrlogin: { token: s.qrToken } });
      return (
        <div className={styles.qrPanel}>
          <div className={styles.qrSteps}>
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>1</span>打开飞书 App
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>2</span>扫码登录
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>3</span>自动创建机器人
            </span>
          </div>
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={qrContent} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>
            扫码后将自动完成机器人创建和配置（约 1-2 分钟）
          </p>
        </div>
      );
    }
    if (s.phase === "feishu_done") {
      const retrySave = () =>
        submitChannel(
          "feishu",
          "feishu",
          mergeDisplayConfig({
            app_id: s.appId,
            app_secret: s.appSecret,
          }),
          true,
        );
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="success"
            message={`飞书机器人「${s.botName ?? ""}」创建成功`}
            style={{ width: "100%", marginBottom: 12 }}
          />
          {s.manageUrl && (
            <a
              href={s.manageUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: 13, marginBottom: 12, display: "block" }}
            >
              前往管理后台 →
            </a>
          )}
          {renderQrAutoSaveStatus(retrySave)}
        </div>
      );
    }
    if (s.phase === "error") {
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="error"
            message={s.reason}
            style={{ width: "100%", marginBottom: 12 }}
          />
          <Button onClick={() => void startFeishuCreator()}>重试</Button>
        </div>
      );
    }
    return (
      <div className={styles.quickConfigPanel}>
        <div className={styles.quickConfigSteps}>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>1</span>
            点击按钮，启动自动创建流程
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>2</span>扫码登录飞书账号
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>3</span>
            自动完成机器人注册和权限配置
          </div>
        </div>
        <Button
          type="primary"
          className={styles.quickConfigBtn}
          block
          onClick={() => void startFeishuCreator("feishu")}
        >
          一键创建飞书机器人
        </Button>
      </div>
    );
  }

  function renderYuanbaoPanel() {
    const s = qrState;
    if (s.phase === "yuanbao_creating" || s.phase === "yuanbao_progress") {
      return (
        <div className={styles.qrPanel}>
          <Spin />
          <p
            style={{
              marginTop: 12,
              color: "var(--fn-text-secondary)",
              fontSize: 13,
            }}
          >
            {s.message}
          </p>
        </div>
      );
    }
    if (s.phase === "yuanbao_scan") {
      const qrValue = s.scanUrl ?? s.scanCode;
      return (
        <div className={styles.qrPanel}>
          <div className={styles.qrSteps}>
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>1</span>打开元宝 App
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>2</span>扫码绑定
            </span>
            <span className={styles.qrStepDivider} />
            <span className={styles.qrStep}>
              <span className={styles.qrDot}>3</span>确认授权
            </span>
          </div>
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={qrValue} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>扫码后在元宝 App 确认绑定</p>
        </div>
      );
    }
    if (s.phase === "yuanbao_done") {
      const retrySave = () =>
        submitChannel(
          "yuanbao",
          "yuanbao",
          mergeDisplayConfig({
            app_key: s.appKey,
            app_secret: s.appSecret,
            api_domain: YUANBAO_DEFAULT_API_DOMAIN,
            ws_url: YUANBAO_DEFAULT_WS_URL,
          }),
          true,
        );
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="success"
            message="元宝机器人绑定成功"
            style={{ width: "100%", marginBottom: 12 }}
          />
          {renderQrAutoSaveStatus(retrySave)}
        </div>
      );
    }
    if (s.phase === "error") {
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="error"
            message={s.reason}
            style={{ width: "100%", marginBottom: 12 }}
          />
          <Button onClick={() => void startYuanbaoCreator()}>重试</Button>
        </div>
      );
    }
    return (
      <div className={styles.quickConfigPanel}>
        <div className={styles.quickConfigSteps}>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>1</span>点击按钮，获取元宝扫码
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>2</span>在元宝 App
            扫码并确认授权
          </div>
          <div className={styles.quickConfigStep}>
            <span className={styles.stepNumber}>3</span>凭据自动填入并保存
          </div>
        </div>
        <Button
          type="primary"
          className={styles.quickConfigBtn}
          block
          onClick={() => void startYuanbaoCreator()}
        >
          生成元宝扫码
        </Button>
      </div>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <Drawer
      width={460}
      placement="right"
      title={
        <div className={styles.drawerTitle}>
          {CHANNEL_ICONS[selectedKind] && (
            <img
              src={CHANNEL_ICONS[selectedKind]}
              alt={kindLabel}
              style={{ width: 22, height: 22 }}
            />
          )}
          <span>{isEdit ? `${kindLabel} 频道设置` : "新建频道"}</span>
        </div>
      }
      open={open}
      onClose={handleClose}
      destroyOnHidden
      footer={
        !loadingConfig ? (
          <div className={styles.drawerFooter}>
            <Button onClick={handleClose}>{t("common.cancel")}</Button>
            {isEdit && onDelete && (
              <Popconfirm
                title={t("channels.deleteConfirmTitle", {
                  name: editing?.id ?? "",
                })}
                okText={t("common.delete")}
                cancelText={t("common.cancel")}
                okButtonProps={{ danger: true }}
                onConfirm={onDelete}
              >
                <Button danger loading={deleting}>
                  {t("common.delete")}
                </Button>
              </Popconfirm>
            )}
            {(isEdit || configMode === "manual" || !supportsQuickConfig) &&
              onTest && (
                <Button
                  icon={<Activity size={14} />}
                  loading={testing}
                  onClick={onTest}
                >
                  {t("channels.checkConnection")}
                </Button>
              )}
            {showFooterSave && (
              <Button
                type="primary"
                loading={saving}
                onClick={() => form.submit()}
              >
                {t("common.save")}
              </Button>
            )}
          </div>
        ) : null
      }
    >
      {loadingConfig ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
          <Spin />
        </div>
      ) : (
        <Form<ChannelFormValues>
          form={form}
          layout="vertical"
          initialValues={initialValues}
          onFinish={handleFinish}
          onValuesChange={(changed, all) => {
            if (changed.kind) setSelectedKind(changed.kind as ChannelKey);
            if (!restoringDraftRef.current && draftScope) {
              saveFormDraft(
                draftScope,
                all as unknown as Record<string, unknown>,
              );
            }
          }}
        >
          {supportsQuickConfig && !isQuickOnly && !isEdit && (
            <Segmented
              className={styles.configModeSwitch}
              block
              value={configMode}
              onChange={(v) => setConfigMode(v as "quick" | "manual")}
              options={[
                { label: "快捷配置（扫码）", value: "quick" },
                { label: "手动填写", value: "manual" },
              ]}
            />
          )}

          {selectedKind === "qq" && <QqGroupContextPolicyFields form={form} />}

          {(configMode === "quick" || isQuickOnly) &&
            supportsQuickConfig &&
            !isEdit && (
              <>
                {selectedKind === "qq" && renderQqPanel()}
                {selectedKind === "wecom" && renderWecomPanel()}
                {selectedKind === "weixin" && renderWeixinPanel()}
                {selectedKind === "feishu" && renderFeishuPanel()}
                {selectedKind === "yuanbao" && renderYuanbaoPanel()}
              </>
            )}

          {(configMode === "manual" || isEdit || !supportsQuickConfig) && (
            <>
              {introUrl && (
                <div className={styles.channelIntroBanner}>
                  <div className={styles.bannerText}>
                    <div className={styles.bannerDesc}>
                      {t(`channels.intro_${selectedKind}`, kindLabel)}
                    </div>
                    <a
                      href={introUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.bannerLink}
                    >
                      前往获取凭据
                      <span className={styles.bannerLinkArrow}>&#8250;</span>
                    </a>
                  </div>
                </div>
              )}

              <Form.Item
                name="kind"
                label="频道类型"
                rules={[{ required: true }]}
              >
                <Select
                  disabled={isEdit}
                  options={CHANNEL_KEYS.map((k) => ({
                    value: k,
                    label: CHANNEL_LABELS[k],
                  }))}
                />
              </Form.Item>

              {isEdit && editing && (
                <Form.Item label="Channel ID">
                  <Input value={editing.id} readOnly />
                </Form.Item>
              )}

              {hasSchema ? (
                fields!.map((f) => <FormItemForField key={f.name} field={f} />)
              ) : (
                <Form.Item
                  name="__raw_config"
                  label="Config (JSON)"
                  tooltip="渠道特定配置 — 详见 harness-gateway 文档"
                  rules={[
                    {
                      validator: (_, value) => {
                        if (!value) return Promise.resolve();
                        try {
                          const parsed = JSON.parse(value);
                          if (
                            !parsed ||
                            typeof parsed !== "object" ||
                            Array.isArray(parsed)
                          ) {
                            return Promise.reject(
                              new Error("必须是 JSON 对象"),
                            );
                          }
                          return Promise.resolve();
                        } catch {
                          return Promise.reject(new Error("非法 JSON"));
                        }
                      },
                    },
                  ]}
                >
                  <Input.TextArea
                    rows={6}
                    placeholder='{"app_id": "…", "app_secret": "…"}'
                  />
                </Form.Item>
              )}
            </>
          )}

          <DisplaySettingsFields />
        </Form>
      )}
    </Drawer>
  );
}
