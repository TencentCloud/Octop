import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Checkbox, Drawer, Input, Spin } from "antd";
import { ChevronDown, ChevronRight } from "lucide-react";
import { message } from "@/utils/antdMessage";
import { useTranslation } from "react-i18next";

import {
  connectorsApi,
  type ConnectorProbeResult,
  type CustomMcpServers,
  type OAuthPendingResult,
} from "../../../api/modules/connectors";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { apiErrorMessage, probeErrorMessage } from "../../../utils/apiError";
import { CustomMcpServerCard } from "./CustomMcpServerCard";
import { pendingOutcome, reportOAuthOutcome } from "./connectorOAuth";
import {
  applyServerJson,
  cardsToServers,
  newCard,
  notifyConnectorsChanged,
  serverJsonText,
  serversToCards,
  type ServerCardState,
} from "./customMcpUtils";
import {
  isAuthPopupBlocked,
  navigateAuthWindow,
  tryOpenAuthPopup,
} from "./openAuthWindow";
import styles from "./index.module.less";

interface CustomMcpDrawerProps {
  open: boolean;
  /** Saved server id. Empty creates a new connector. */
  serverName: string | null;
  avatarUrl?: string | null;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

const SERVER_ID = /^[A-Za-z0-9_-]+$/;

export function CustomMcpDrawer({
  open,
  serverName,
  avatarUrl,
  onClose,
  onSaved,
}: CustomMcpDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const editing = Boolean(serverName);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [probing, setProbing] = useState(false);
  const [authorizing, setAuthorizing] = useState(false);
  const [card, setCard] = useState<ServerCardState>(() =>
    newCard("streamable_http", 0),
  );
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [removePhoto, setRemovePhoto] = useState(false);
  const [probeTools, setProbeTools] = useState<
    { name: string; description: string }[] | undefined
  >(undefined);
  const [oauthAvailable, setOauthAvailable] = useState(false);
  const [oauthClientRequired, setOauthClientRequired] = useState(false);
  const [probeOnSave, setProbeOnSave] = useState(false);
  const [jsonOpen, setJsonOpen] = useState(false);
  const [jsonDraft, setJsonDraft] = useState<string | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const jsonFocused = useRef(false);

  const resetJson = useCallback(() => {
    setJsonOpen(false);
    setJsonDraft(null);
    setJsonError(null);
    jsonFocused.current = false;
  }, []);

  const resetBlank = useCallback(() => {
    setCard({ ...newCard("streamable_http", 0), collapsed: false });
    setPhotoUrl(null);
    setPendingFile(null);
    setRemovePhoto(false);
    setProbeTools(undefined);
    setOauthAvailable(false);
    setOauthClientRequired(false);
    resetJson();
  }, [resetJson]);

  useEffect(() => {
    if (!open) return;
    setProbeTools(undefined);
    setOauthAvailable(false);
    setOauthClientRequired(false);
    setPendingFile(null);
    setRemovePhoto(false);
    resetJson();
    if (!serverName) {
      resetBlank();
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void connectorsApi
      .getCustomMcp()
      .then(({ servers }) => {
        if (cancelled) return;
        const spec = servers[serverName];
        if (!spec) {
          message.error(
            t("connectors.customMcp.loadFailed", "加载自定义 MCP 失败"),
          );
          return;
        }
        const [loaded] = serversToCards({ [serverName]: spec });
        setCard({ ...loaded, collapsed: false });
        setPhotoUrl(avatarUrl ?? null);
      })
      .catch((error) => {
        if (cancelled) return;
        message.error(
          apiErrorMessage(
            error,
            t("connectors.customMcp.loadFailed", "加载自定义 MCP 失败"),
            t,
          ),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, serverName, avatarUrl, resetBlank, resetJson, t]);

  const jsonMessage = useCallback(
    (error: unknown): string => {
      const code = error instanceof Error ? error.message : "";
      if (code === "json_shape") {
        return t(
          "connectors.customMcp.jsonShape",
          "需要是单个服务器的配置，或「服务器 ID」对应一段配置",
        );
      }
      if (code === "name_locked") {
        return t(
          "connectors.customMcp.jsonNameLocked",
          "已保存的服务器 ID 不能在 JSON 里修改",
        );
      }
      if (code === "empty_name") {
        return t("connectors.customMcp.emptyName", "请填写服务器 ID");
      }
      return t("connectors.customMcp.jsonInvalid", "JSON 格式无效");
    },
    [t],
  );

  const generatedJson = useMemo(() => serverJsonText(card), [card]);
  const jsonText = jsonDraft ?? generatedJson;

  const updateCard = (key: string, patch: Partial<ServerCardState>) => {
    setCard((prev) => (prev.key === key ? { ...prev, ...patch } : prev));
    if (!jsonFocused.current) {
      setJsonDraft(null);
      setJsonError(null);
    }
  };

  const onJsonChange = (value: string) => {
    setJsonDraft(value);
    try {
      setCard(applyServerJson(value, card, { nameLocked: editing }));
      setJsonError(null);
    } catch (error) {
      setJsonError(jsonMessage(error));
    }
  };

  const transportOptions = useMemo(
    () => [
      { value: "streamable_http", label: "streamable_http" },
      { value: "stdio", label: "stdio" },
    ],
    [],
  );

  const applyProbeResult = (
    current: ServerCardState,
    result: ConnectorProbeResult,
  ) => {
    if (result.ok) {
      setProbeTools(result.tools ?? []);
      setOauthAvailable(false);
      setOauthClientRequired(false);
      if ((result.tools ?? []).length === 0) {
        message.success(
          t("connectors.probeToolsEmpty", "连接正常，但未发现可用工具"),
        );
      } else {
        message.success(t("connectors.customMcp.probeComplete", "连接正常"));
      }
      return;
    }
    setProbeTools(undefined);
    if (result.oauth?.available) {
      setOauthAvailable(true);
      setCard((prev) =>
        prev.key === current.key
          ? { ...prev, enabled: false, defaultOpen: false }
          : prev,
      );
      message.warning(
        t(
          "connectors.customMcp.probeNeedsOAuth",
          "此 MCP 需要 OAuth 授权才能访问",
        ),
      );
      return;
    }
    setOauthAvailable(false);
    if (result.oauth?.client_required) {
      setOauthClientRequired(true);
      setCard((prev) =>
        prev.key === current.key
          ? {
              ...prev,
              oauthClientOpen: true,
              enabled: false,
              defaultOpen: false,
            }
          : prev,
      );
      message.warning(
        t(
          "connectors.customMcp.probeNeedsOAuthClient",
          "此 MCP 的授权服务器不支持自动注册客户端",
        ),
      );
      return;
    }
    message.error(
      probeErrorMessage(result, t("connectors.probeFailed", "探测失败"), t),
    );
  };

  const validateCard = (current: ServerCardState): boolean => {
    if (jsonError) {
      message.warning(jsonError);
      return false;
    }
    const name = current.name.trim();
    if (!name || !SERVER_ID.test(name)) {
      message.warning(t("connectors.customMcp.emptyName", "请填写服务器 ID"));
      return false;
    }
    if (current.visibility === "groups" && current.groupIds.length === 0) {
      message.warning(t("resourceVisibility.needGroup"));
      return false;
    }
    try {
      cardsToServers([current]);
    } catch (error) {
      message.warning(
        apiErrorMessage(
          error,
          t("connectors.customMcp.visualInvalid", "请检查配置后重试"),
          t,
        ),
      );
      return false;
    }
    return true;
  };

  const persist = async (current: ServerCardState): Promise<boolean> => {
    if (!validateCard(current)) return false;
    const name = current.name.trim();
    const spec = cardsToServers([current])[name];
    const { servers } = await connectorsApi.getCustomMcp();
    const next: CustomMcpServers = { ...servers };
    if (serverName && serverName !== name) {
      delete next[serverName];
    }
    next[name] = spec;
    await connectorsApi.putCustomMcp(next);
    if (pendingFile) {
      try {
        const uploaded = await connectorsApi.uploadCustomMcpAvatar(
          name,
          pendingFile,
        );
        setPhotoUrl(uploaded.avatar_url);
        setPendingFile(null);
        setRemovePhoto(false);
      } catch (error) {
        message.warning(
          apiErrorMessage(
            error,
            t(
              "connectors.customMcp.avatarUploadFailed",
              "连接器已保存，头像上传失败",
            ),
            t,
          ),
        );
      }
    } else if (removePhoto) {
      try {
        await connectorsApi.deleteCustomMcpAvatar(name);
        setRemovePhoto(false);
      } catch {
        // The preset still applies. A leftover photo can be removed later.
      }
    }
    notifyConnectorsChanged();
    return true;
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const ok = await persist(card);
      if (!ok) return;
      message.success(
        editing
          ? t("connectors.saveSuccess", "连接器已保存")
          : t("connectors.createSuccess", "连接器已创建"),
      );
      await onSaved();
      if (
        probeOnSave &&
        card.transport === "streamable_http" &&
        card.url.trim()
      ) {
        setProbing(true);
        try {
          const result = await connectorsApi.testCustomMcp({
            name: card.name.trim(),
          });
          applyProbeResult(card, result);
        } catch (error) {
          message.error(
            apiErrorMessage(error, t("connectors.probeFailed", "探测失败"), t),
          );
        } finally {
          setProbing(false);
        }
        return;
      }
      onClose();
    } catch (error) {
      message.error(
        apiErrorMessage(
          error,
          t("connectors.customMcp.saveFailed", "保存失败"),
          t,
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleProbe = async () => {
    if (!validateCard(card)) return;
    setProbing(true);
    setProbeTools(undefined);
    try {
      let result: ConnectorProbeResult;
      if (editing && card.oauthConfigured && !pendingFile) {
        result = await connectorsApi.testCustomMcp({ name: card.name.trim() });
      } else {
        const spec = cardsToServers([card])[card.name.trim()];
        result = await connectorsApi.testCustomMcp({ server: spec });
      }
      applyProbeResult(card, result);
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("connectors.probeFailed", "探测失败"), t),
      );
    } finally {
      setProbing(false);
    }
  };

  const handleOAuth = async () => {
    if (!validateCard(card)) return;
    const popup = tryOpenAuthPopup("", "octop-oauth", "width=520,height=720");
    if (isAuthPopupBlocked(popup)) {
      message.error(
        t(
          "connectors.oauthPopupBlocked",
          "授权窗口被浏览器拦截，请允许本站弹出窗口后重试",
        ),
      );
      return;
    }
    setAuthorizing(true);
    let settled = false;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let timeoutTimer: ReturnType<typeof setTimeout> | undefined;
    let stateId = "";
    const name = card.name.trim();

    const cleanup = () => {
      if (pollTimer !== undefined) clearInterval(pollTimer);
      if (timeoutTimer !== undefined) clearTimeout(timeoutTimer);
      window.removeEventListener("message", onMessage);
    };

    const finish = async () => {
      if (settled) return;
      settled = true;
      cleanup();
      try {
        popup?.close();
      } catch {
        // ignore
      }
      setAuthorizing(false);
      try {
        const { servers } = await connectorsApi.getCustomMcp();
        const spec = servers[name];
        if (spec) {
          const [loaded] = serversToCards({ [name]: spec });
          setCard({ ...loaded, key: card.key, collapsed: false });
        }
        const result = await connectorsApi.testCustomMcp({ name });
        applyProbeResult(card, result);
        notifyConnectorsChanged();
        await onSaved();
        message.success(
          t("connectors.oauthConfigured", "已授权，可直接探测或保存"),
        );
      } catch (error) {
        message.error(
          apiErrorMessage(
            error,
            t("connectors.oauthFailed", "获取授权结果失败"),
            t,
          ),
        );
      }
    };

    const claimPending = async () => {
      if (!stateId || settled) return;
      let pending: OAuthPendingResult;
      try {
        pending = await connectorsApi.oauthPending(stateId);
      } catch {
        return;
      }
      const outcome = pendingOutcome(pending);
      if (outcome.status !== "ok") {
        settled = true;
        cleanup();
        setAuthorizing(false);
        reportOAuthOutcome(outcome, t);
        return;
      }
      if (pending.applied || pending.server_name) {
        await finish();
      }
    };

    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "octop:connector-oauth") return;
      if (event.data.state_id !== stateId) return;
      void claimPending();
    };

    try {
      const ok = await persist(card);
      if (!ok) {
        popup?.close();
        setAuthorizing(false);
        return;
      }
      await onSaved();
      const started = await connectorsApi.oauthStart(
        { type: "custom_mcp", server_name: name },
        window.location.pathname,
      );
      stateId = started.state_id;
      window.addEventListener("message", onMessage);
      pollTimer = setInterval(() => {
        void claimPending();
      }, 1200);
      timeoutTimer = setTimeout(() => {
        if (settled) return;
        settled = true;
        cleanup();
        setAuthorizing(false);
        message.error(
          t("connectors.oauthTimedOut", "授权超时，请重试一键授权"),
        );
      }, 120_000);
      navigateAuthWindow(popup, started.authorize_url);
    } catch (error) {
      cleanup();
      setAuthorizing(false);
      try {
        popup?.close();
      } catch {
        // ignore
      }
      message.error(
        apiErrorMessage(
          error,
          t("connectors.oauthStartFailed", "无法启动 OAuth"),
          t,
        ),
      );
    }
  };

  const title = editing
    ? t("connectors.customMcp.drawerEdit", {
        name: card.displayName.trim() || card.name.trim() || serverName,
        defaultValue: "编辑自定义连接器",
      })
    : t("connectors.addCustom", "添加自定义连接器");

  return (
    <Drawer
      title={title}
      placement="right"
      open={open}
      onClose={onClose}
      width={isMobile ? "100%" : 640}
      destroyOnHidden
      footer={
        <div className={styles.customDrawerFooter}>
          {card.transport === "streamable_http" ? (
            <Checkbox
              checked={probeOnSave}
              onChange={(event) => setProbeOnSave(event.target.checked)}
            >
              {t("connectors.customMcp.probeOnSave", "保存后自动探测连接")}
            </Checkbox>
          ) : (
            <span />
          )}
          <div className={styles.customDrawerFooterActions}>
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            {card.transport === "streamable_http" ? (
              <Button loading={probing} onClick={() => void handleProbe()}>
                {t("connectors.probe", "探测")}
              </Button>
            ) : null}
            <Button
              type="primary"
              loading={saving}
              onClick={() => void handleSave()}
            >
              {editing ? t("common.save") : t("common.create")}
            </Button>
          </div>
        </div>
      }
    >
      {loading ? (
        <div className={styles.loadingState}>
          <Spin />
        </div>
      ) : (
        <CustomMcpServerCard
          card={card}
          probing={probing}
          authorizing={authorizing}
          oauthAvailable={oauthAvailable}
          oauthClientRequired={oauthClientRequired}
          probeTools={probeTools}
          transportOptions={transportOptions}
          embedded
          nameLocked={editing}
          avatarUrl={photoUrl}
          onUpdate={updateCard}
          onToggleEnabled={(enabled) => {
            if (
              (oauthAvailable || oauthClientRequired) &&
              !card.oauthConfigured &&
              enabled
            ) {
              message.warning(
                t(
                  "connectors.customMcp.oauthBeforeEnable",
                  "请先完成 OAuth 授权后再启用",
                ),
              );
              return;
            }
            updateCard(card.key, {
              enabled,
              ...(enabled ? {} : { defaultOpen: false }),
            });
          }}
          onRemove={() => undefined}
          onProbe={() => void handleProbe()}
          onAuthorize={() => void handleOAuth()}
          onPickAvatar={(file) => {
            setPendingFile(file);
            setRemovePhoto(false);
            setPhotoUrl(URL.createObjectURL(file));
            updateCard(card.key, { avatarIcon: "" });
          }}
          onSelectAvatarPreset={(presetId) => {
            setPendingFile(null);
            setPhotoUrl(null);
            setRemovePhoto(true);
            updateCard(card.key, { avatarIcon: presetId ?? "" });
          }}
          onRemoveAvatar={() => {
            setPendingFile(null);
            setPhotoUrl(null);
            setRemovePhoto(true);
          }}
        />
      )}
      {!loading ? (
        <div className={styles.customJsonFold}>
          <button
            type="button"
            className={styles.customJsonToggle}
            aria-expanded={jsonOpen}
            onClick={() => {
              setJsonOpen((opened) => {
                if (!opened) {
                  setJsonDraft(null);
                  setJsonError(null);
                }
                return !opened;
              });
            }}
          >
            {jsonOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {t("connectors.customMcp.jsonToggle", "JSON")}
          </button>
          {jsonOpen ? (
            <div className={styles.customMcpJsonEditor}>
              <p className={styles.customJsonHint}>
                {t(
                  "connectors.customMcp.jsonHint",
                  "当前连接器的原始 JSON。修改后会同步到上方表单。",
                )}
              </p>
              <Input.TextArea
                className={styles.customMcpJsonArea}
                value={jsonText}
                autoSize={{ minRows: 8, maxRows: 16 }}
                spellCheck={false}
                onFocus={() => {
                  jsonFocused.current = true;
                }}
                onBlur={() => {
                  jsonFocused.current = false;
                  setJsonDraft((draft) => {
                    if (draft == null) return null;
                    try {
                      applyServerJson(draft, card, { nameLocked: editing });
                      setJsonError(null);
                      return null;
                    } catch (error) {
                      setJsonError(jsonMessage(error));
                      return draft;
                    }
                  });
                }}
                onChange={(event) => onJsonChange(event.target.value)}
              />
              {jsonError ? (
                <div className={styles.customMcpJsonError}>{jsonError}</div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  );
}
