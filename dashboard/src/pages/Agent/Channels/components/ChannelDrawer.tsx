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
  "dingtalk",
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
  | {
      phase: "dingtalk_ready";
      qrcodeUrl: string;
      userCode: string;
    }
  | { phase: "dingtalk_success"; channelId: string }
  | { phase: "feishu_creating"; message: string }
  | { phase: "feishu_qr"; qrUrl: string }
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
  onProvisioned: () => void;
  onTest?: () => void;
  testing?: boolean;
  agentId: string;
}

function FormItemForField({ field }: { field: ChannelField }) {
  const { t } = useTranslation();
  const Input1 =
    field.type === "password"
      ? Input.Password
      : field.type === "textarea" || field.type === "json"
      ? Input.TextArea
      : Input;
  const rules: Rule[] = field.required
    ? [
        {
          required: true,
          message: t("channels.fieldRequired", { label: field.label }),
        },
      ]
    : [];
  if (field.type === "json") {
    rules.push({
      validator: async (_: unknown, value: unknown) => {
        if (!value) return;
        try {
          normalizeChannelFieldValue(field.name, value);
        } catch {
          throw new Error(
            t("channels.fieldMustBeJsonObject", { label: field.label }),
          );
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
  onProvisioned,
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
    if (open && initialValues?.kind) {
      setSelectedKind(initialValues.kind);
    }
  }, [open, initialValues?.kind]);

  // Only wipe an in-flight QR when the kind actually changes while the drawer
  // is already open. A blanket `[selectedKind]` reset races the open-time
  // kickoff: QR appears, kind sync/draft fires, resetQr hides it, and a second
  // start often never gets a new qr_url.
  const kindWhileOpenRef = useRef<ChannelKey | null>(null);
  useEffect(() => {
    if (!open) {
      kindWhileOpenRef.current = null;
      return;
    }
    if (kindWhileOpenRef.current === null) {
      kindWhileOpenRef.current = selectedKind;
      return;
    }
    if (kindWhileOpenRef.current === selectedKind) return;
    kindWhileOpenRef.current = selectedKind;
    resetQr();
  }, [open, selectedKind, resetQr]);

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
  const startQqQr = async () => {
    stopPolling();
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
  };

  // ── WeCom Flow ─────────────────────────────────────────────────────────
  const startWecomQr = async () => {
    stopPolling();
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
            setQrState({
              phase: "error",
              reason: poll.reason ?? t("channels.qrFailed"),
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
  };

  // ── WeChat Flow ─────────────────────────────────────────────────────────
  const startWeixinQr = async () => {
    stopPolling();
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
            setQrState({
              phase: "error",
              reason: poll.message ?? t("channels.qrFailed"),
            });
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
  };

  // ── DingTalk Flow ───────────────────────────────────────────────────────
  const startDingtalkQr = async () => {
    stopPolling();
    setQrState({ phase: "loading" });
    try {
      const res = await channelApi.dingtalkQrcodeGenerate(agentId);
      setQrState({
        phase: "dingtalk_ready",
        qrcodeUrl: res.qrcode_url,
        userCode: res.user_code,
      });
      let polling = false;
      const timer = setInterval(
        async () => {
          if (polling) return;
          polling = true;
          try {
            const poll = await channelApi.dingtalkQrcodePoll(
              agentId,
              res.registration_id,
            );
            if (poll.status === "success" && poll.channel_id) {
              stopPolling();
              setQrState({
                phase: "dingtalk_success",
                channelId: poll.channel_id,
              });
              onProvisioned();
            } else if (poll.status === "failed" || poll.status === "expired") {
              stopPolling();
              setQrState({
                phase: "error",
                reason:
                  poll.message ??
                  (poll.status === "expired"
                    ? t("channels.dingtalkQrExpired")
                    : t("channels.dingtalkQrFailed")),
              });
            }
          } catch {
            // Transient network error: keep polling until DingTalk expires the flow.
          } finally {
            polling = false;
          }
        },
        Math.max(1000, res.interval * 1000),
      );
      pollTimerRef.current = timer;
    } catch (e: unknown) {
      setQrState({
        phase: "error",
        reason: e instanceof Error ? e.message : String(e),
      });
    }
  };

  // ── Feishu Flow ─────────────────────────────────────────────────────────
  const startFeishuCreator = async (
    platform: "feishu" | "lark" = "feishu",
  ) => {
    stopPolling();
    setQrState({
      phase: "feishu_creating",
      message: t("channels.feishuCreating"),
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
        if (poll.qr_url) {
          setQrState((prev) =>
            prev.phase === "feishu_progress" || prev.phase === "feishu_done"
              ? prev
              : { phase: "feishu_qr", qrUrl: poll.qr_url! },
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
            reason: errEvent?.message ?? t("channels.feishuCreateFailed"),
          });
        }
      } catch {
        // keep polling
      }
    }, 1500);
    pollTimerRef.current = timer;
  };

  // ── YuanBao Flow ────────────────────────────────────────────────────────
  const startYuanbaoCreator = async () => {
    stopPolling();
    setQrState({
      phase: "yuanbao_creating",
      message: t("channels.yuanbaoStarting"),
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
            reason: errEvent?.message ?? t("channels.yuanbaoBindFailed"),
          });
        }
      } catch {
        // keep polling
      }
    }, 2000);
    pollTimerRef.current = timer;
  };

  // Entering quick-config starts QR generation immediately (no extra click).
  useEffect(() => {
    if (!open || isEdit || loadingConfig) return;
    if (configMode !== "quick" && selectedKind !== "weixin") return;
    if (qrState.phase !== "idle") return;
    // Wait until local kind matches the card that opened the drawer.
    if (initialValues?.kind && selectedKind !== initialValues.kind) return;

    switch (selectedKind) {
      case "qq":
        void startQqQr();
        break;
      case "wecom":
        void startWecomQr();
        break;
      case "weixin":
        void startWeixinQr();
        break;
      case "dingtalk":
        void startDingtalkQr();
        break;
      case "feishu":
        void startFeishuCreator("feishu");
        break;
      case "yuanbao":
        void startYuanbaoCreator();
        break;
      default:
        break;
    }
    // start* omitted: recreated each render; idle-phase already one-shots.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    open,
    isEdit,
    loadingConfig,
    configMode,
    selectedKind,
    qrState.phase,
    initialValues?.kind,
  ]);

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
            {t("channels.qrAutoSaving")}
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
          {t("channels.qrRetrySave")}
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
  function renderQrSteps(step1: string, step2: string, step3: string) {
    return (
      <div className={styles.qrSteps}>
        <span className={styles.qrStep}>
          <span className={styles.qrDot}>1</span>
          {step1}
        </span>
        <span className={styles.qrStepDivider} />
        <span className={styles.qrStep}>
          <span className={styles.qrDot}>2</span>
          {step2}
        </span>
        <span className={styles.qrStepDivider} />
        <span className={styles.qrStep}>
          <span className={styles.qrDot}>3</span>
          {step3}
        </span>
      </div>
    );
  }

  function renderQrLoading(step1: string, step2: string, step3: string) {
    return (
      <div className={styles.qrPanel}>
        {renderQrSteps(step1, step2, step3)}
        <div className={styles.qrCardWrap}>
          <div className={styles.qrFrame}>
            <Spin />
          </div>
        </div>
        <p className={styles.qrScanHint}>{t("channels.qrLoading")}</p>
      </div>
    );
  }

  function renderQqPanel() {
    const s = qrState;
    if (s.phase === "loading" || s.phase === "idle")
      return renderQrLoading(
        t("channels.qqQrStep1"),
        t("channels.qqQrStep2"),
        t("channels.qqQrStep3"),
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
          {renderQrSteps(
            t("channels.qqQrStep1"),
            t("channels.qqQrStep2"),
            t("channels.qqQrStep3"),
          )}
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={s.qrcodeUrl} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>{t("channels.qqQrScanHint")}</p>
          <Button
            size="small"
            onClick={() => void startQqQr()}
            style={{ marginTop: 4 }}
          >
            {t("channels.qrRegenerate")}
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
            {t("channels.qrRegenerate")}
          </Button>
        </div>
      );
    }
    return null;
  }

  function renderWecomPanel() {
    const s = qrState;
    if (s.phase === "loading" || s.phase === "idle")
      return renderQrLoading(
        t("channels.qrStep1"),
        t("channels.qrStep2"),
        t("channels.qrStep3"),
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
            message={t("channels.wecomQrSuccess")}
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
          {renderQrSteps(
            t("channels.qrStep1"),
            t("channels.qrStep2"),
            t("channels.qrStep3"),
          )}
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={s.authUrl} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>{t("channels.qrScanHint")}</p>
          <Button
            size="small"
            onClick={() => void startWecomQr()}
            style={{ marginTop: 4 }}
          >
            {t("channels.qrRegenerate")}
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
          <Button onClick={() => void startWecomQr()}>
            {t("channels.qrRetryBtn")}
          </Button>
        </div>
      );
    }
    return null;
  }

  function renderWeixinPanel() {
    const s = qrState;
    if (s.phase === "loading" || s.phase === "idle")
      return renderQrLoading(
        t("channels.weixinQrStep1"),
        t("channels.weixinQrStep2"),
        t("channels.weixinQrStep3"),
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
            message={t("channels.weixinQrSuccess")}
            description={t("channels.weixinAccountId", { id: s.accountId })}
            style={{ width: "100%", marginBottom: 12 }}
          />
          {renderQrAutoSaveStatus(retrySave)}
        </div>
      );
    }
    if (s.phase === "weixin_ready") {
      return (
        <div className={styles.qrPanel}>
          {renderQrSteps(
            t("channels.weixinQrStep1"),
            t("channels.weixinQrStep2"),
            t("channels.weixinQrStep3"),
          )}
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={s.qrcodeUrl} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>{t("channels.weixinQrScanHint")}</p>
          <Button
            size="small"
            onClick={() => void startWeixinQr()}
            style={{ marginTop: 4 }}
          >
            {t("channels.qrRegenerate")}
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
          <Button onClick={() => void startWeixinQr()}>
            {t("channels.qrRetryBtn")}
          </Button>
        </div>
      );
    }
    return null;
  }

  function renderDingtalkPanel() {
    const s = qrState;
    if (s.phase === "loading" || s.phase === "idle") {
      return renderQrLoading(
        t("channels.dingtalkQrStep1"),
        t("channels.dingtalkQrStep2"),
        t("channels.dingtalkQrStep3"),
      );
    }
    if (s.phase === "dingtalk_success") {
      return (
        <div className={styles.qrPanel}>
          <Alert
            type="success"
            message={t("channels.dingtalkBindSuccess")}
            style={{ width: "100%" }}
          />
        </div>
      );
    }
    if (s.phase === "dingtalk_ready") {
      return (
        <div className={styles.qrPanel}>
          {renderQrSteps(
            t("channels.dingtalkQrStep1"),
            t("channels.dingtalkQrStep2"),
            t("channels.dingtalkQrStep3"),
          )}
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={s.qrcodeUrl} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>
            {t("channels.dingtalkQrScanHint")}
          </p>
          <p className={styles.qrScanHint}>
            {t("channels.dingtalkUserCode")}: <code>{s.userCode}</code>
          </p>
          <Button
            size="small"
            onClick={() => void startDingtalkQr()}
            style={{ marginTop: 4 }}
          >
            {t("channels.qrRegenerate")}
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
          <Button onClick={() => void startDingtalkQr()}>
            {t("channels.qrRetryBtn")}
          </Button>
        </div>
      );
    }
    return null;
  }

  function renderFeishuPanel() {
    const s = qrState;
    const feishuPending =
      s.phase === "idle" ||
      s.phase === "loading" ||
      s.phase === "feishu_creating" ||
      s.phase === "feishu_progress";
    if (feishuPending || s.phase === "feishu_qr") {
      return (
        <div className={styles.qrPanel}>
          {renderQrSteps(
            t("channels.feishuQrStep1"),
            t("channels.feishuQrStep2"),
            t("channels.feishuQrStep3"),
          )}
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              {s.phase === "feishu_qr" ? (
                <QRCodeSVG value={s.qrUrl} size={200} />
              ) : (
                <Spin />
              )}
            </div>
          </div>
          <p className={styles.qrScanHint}>
            {s.phase === "feishu_qr"
              ? t("channels.feishuQrScanHint")
              : t("channels.qrLoading")}
          </p>
          <Button
            size="small"
            style={{
              marginTop: 4,
              visibility: s.phase === "feishu_qr" ? "visible" : "hidden",
            }}
            onClick={() => void startFeishuCreator()}
          >
            {t("channels.qrRegenerate")}
          </Button>
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
            message={
              s.botName
                ? t("channels.feishuCreateSuccessNamed", { name: s.botName })
                : t("channels.feishuCreateSuccess")
            }
            style={{ width: "100%", marginBottom: 12 }}
          />
          {s.manageUrl && (
            <a
              href={s.manageUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: 13, marginBottom: 12, display: "block" }}
            >
              {t("channels.feishuManageBot")}
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
          <Button onClick={() => void startFeishuCreator()}>
            {t("channels.qrRegenerate")}
          </Button>
        </div>
      );
    }
    return renderQrLoading(
      t("channels.feishuQrStep1"),
      t("channels.feishuQrStep2"),
      t("channels.feishuQrStep3"),
    );
  }

  function renderYuanbaoPanel() {
    const s = qrState;
    if (
      s.phase === "idle" ||
      s.phase === "loading" ||
      s.phase === "yuanbao_creating" ||
      s.phase === "yuanbao_progress"
    ) {
      return renderQrLoading(
        t("channels.yuanbaoQrStep1"),
        t("channels.yuanbaoQrStep2"),
        t("channels.yuanbaoQrStep3"),
      );
    }
    if (s.phase === "yuanbao_scan") {
      const qrValue = s.scanUrl ?? s.scanCode;
      return (
        <div className={styles.qrPanel}>
          {renderQrSteps(
            t("channels.yuanbaoQrStep1"),
            t("channels.yuanbaoQrStep2"),
            t("channels.yuanbaoQrStep3"),
          )}
          <div className={styles.qrCardWrap}>
            <div className={styles.qrFrame}>
              <QRCodeSVG value={qrValue} size={200} />
            </div>
          </div>
          <p className={styles.qrScanHint}>{t("channels.yuanbaoQrScanHint")}</p>
          <Button
            size="small"
            onClick={() => void startYuanbaoCreator()}
            style={{ marginTop: 4 }}
          >
            {t("channels.qrRegenerate")}
          </Button>
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
            message={t("channels.yuanbaoCreateSuccess")}
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
          <Button onClick={() => void startYuanbaoCreator()}>
            {t("channels.qrRetryBtn")}
          </Button>
        </div>
      );
    }
    return renderQrLoading(
      t("channels.yuanbaoQrStep1"),
      t("channels.yuanbaoQrStep2"),
      t("channels.yuanbaoQrStep3"),
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
          <span>
            {isEdit
              ? t("channels.channelSettingsNamed", { kind: kindLabel })
              : t("channels.createChannel")}
          </span>
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
                { label: t("channels.quickConfig"), value: "quick" },
                { label: t("channels.manualConfig"), value: "manual" },
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
                {selectedKind === "dingtalk" && renderDingtalkPanel()}
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
                      {t("channels.getCredentials")}
                      <span className={styles.bannerLinkArrow}>&#8250;</span>
                    </a>
                  </div>
                </div>
              )}

              <Form.Item
                name="kind"
                label={t("channels.channelType")}
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
                  tooltip={t("channels.rawConfigTooltip")}
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
                              new Error(t("channels.jsonMustBeObject")),
                            );
                          }
                          return Promise.resolve();
                        } catch {
                          return Promise.reject(
                            new Error(t("channels.invalidJson")),
                          );
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
