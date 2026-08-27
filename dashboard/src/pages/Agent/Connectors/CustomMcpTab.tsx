import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Checkbox, Input, Segmented, Spin } from "antd";
import { message } from "@/utils/antdMessage";

import { Globe, Plus, Terminal } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  connectorsApi,
  type ConnectorProbeResult,
  type CustomMcpServers,
  type CustomMcpTransport,
} from "../../../api/modules/connectors";
import { apiErrorMessage } from "../../../utils/apiError";
import { CustomMcpServerCard } from "./CustomMcpServerCard";
import {
  EXAMPLE_JSON,
  PROBE_ON_SAVE_KEY,
  cardsToServers,
  hasHttpProbeTargets,
  mergeCustomMcpCards,
  newCard,
  notifyConnectorsChanged,
  oauthHintsFromServers,
  serversToCards,
  type EditorMode,
  type ServerCardState,
} from "./customMcpUtils";
import styles from "./index.module.less";

export function CustomMcpTab() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [probingKey, setProbingKey] = useState<string | null>(null);
  const [probeResults, setProbeResults] = useState<
    Record<string, { name: string; description: string }[]>
  >({});
  const [mode, setMode] = useState<EditorMode>("visual");
  const [cards, setCards] = useState<ServerCardState[]>([]);
  const [jsonText, setJsonText] = useState("{}");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [probeOnSave, setProbeOnSave] = useState(
    () => localStorage.getItem(PROBE_ON_SAVE_KEY) === "1",
  );
  const [oauthAvailable, setOauthAvailable] = useState<Record<string, boolean>>(
    {},
  );
  const [authorizingKey, setAuthorizingKey] = useState<string | null>(null);
  const [persistedNames, setPersistedNames] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    localStorage.setItem(PROBE_ON_SAVE_KEY, probeOnSave ? "1" : "0");
  }, [probeOnSave]);

  const applySavedServers = (
    servers: CustomMcpServers,
    prevCards: ServerCardState[],
  ) => {
    const nextCards = mergeCustomMcpCards(servers, prevCards);
    setCards(nextCards);
    setPersistedNames(new Set(Object.keys(servers)));
    setJsonText(JSON.stringify(servers, null, 2));
    setOauthAvailable(oauthHintsFromServers(servers, nextCards));
    return nextCards;
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { servers } = await connectorsApi.getCustomMcp();
      applySavedServers(servers, []);
      setProbeResults({});
      setJsonError(null);
    } catch (e) {
      console.error(e);
      message.error(
        apiErrorMessage(
          e,
          t("connectors.customMcp.loadFailed", "加载自定义 MCP 失败"),
          t,
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const persistServerPatch = async (
    card: ServerCardState,
    apiPatch: { enabled?: boolean; default_open?: boolean },
    localPatch: Partial<ServerCardState>,
  ) => {
    const optimisticCards = cards.map((item) =>
      item.key === card.key ? { ...item, ...localPatch } : item,
    );
    updateCard(card.key, localPatch);
    const name = card.name.trim();
    if (!name || !persistedNames.has(name)) {
      return;
    }
    try {
      const { servers } = await connectorsApi.patchCustomMcpServer(
        name,
        apiPatch,
      );
      applySavedServers(servers, optimisticCards);
      notifyConnectorsChanged();
    } catch (e) {
      console.error(e);
      message.error(
        apiErrorMessage(e, t("connectors.customMcp.saveFailed", "保存失败"), t),
      );
      await load();
    }
  };

  const syncJsonFromCards = useCallback((nextCards: ServerCardState[]) => {
    try {
      const servers = cardsToServers(nextCards);
      setJsonText(JSON.stringify(servers, null, 2));
      setJsonError(null);
    } catch {
      // keep previous json while visual has incomplete names
    }
  }, []);

  const updateCard = (key: string, patch: Partial<ServerCardState>) => {
    setCards((prev) => {
      const next = prev.map((card) =>
        card.key === key ? { ...card, ...patch } : card,
      );
      syncJsonFromCards(next);
      return next;
    });
  };

  const handleModeChange = (nextMode: EditorMode) => {
    if (nextMode === mode) return;
    if (nextMode === "json") {
      try {
        const servers = cardsToServers(cards);
        setJsonText(JSON.stringify(servers, null, 2));
        setJsonError(null);
      } catch (e) {
        message.warning(
          t(
            "connectors.customMcp.visualInvalid",
            "可视化配置不完整，请先修正名称与必填项",
          ),
        );
        console.error(e);
        return;
      }
    } else {
      try {
        const parsed = JSON.parse(jsonText) as unknown;
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("root must be object");
        }
        const servers = parsed as CustomMcpServers;
        setCards(serversToCards(servers));
        setJsonError(null);
      } catch {
        setJsonError(
          t(
            "connectors.customMcp.jsonInvalid",
            "JSON 格式无效，无法切换到可视化",
          ),
        );
        message.error(
          t(
            "connectors.customMcp.jsonInvalid",
            "JSON 格式无效，无法切换到可视化",
          ),
        );
        return;
      }
    }
    setMode(nextMode);
  };

  const handleAdd = (transport: CustomMcpTransport) => {
    setCards((prev) => {
      const next = [...prev, newCard(transport, prev.length)];
      syncJsonFromCards(next);
      return next;
    });
    setMode("visual");
  };

  const handleRemove = async (key: string) => {
    const card = cards.find((item) => item.key === key);
    const serverName = card?.name.trim() ?? "";
    const nextCards = cards.filter((item) => item.key !== key);
    setCards(nextCards);
    syncJsonFromCards(nextCards);
    setProbeResults((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setOauthAvailable((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });

    if (!serverName || !persistedNames.has(serverName)) {
      return;
    }

    try {
      await connectorsApi.deleteInstance(`custom:${serverName}`);
      setPersistedNames((prev) => {
        const next = new Set(prev);
        next.delete(serverName);
        return next;
      });
      notifyConnectorsChanged();
      message.success(t("connectors.deleteSuccess", "已删除"));
    } catch (e) {
      console.error(e);
      message.error(
        apiErrorMessage(e, t("connectors.deleteFailed", "删除失败"), t),
      );
      await load();
    }
  };

  const clearProbeResult = (key: string) => {
    setProbeResults((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setOauthAvailable((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const applyProbeResult = (
    card: ServerCardState,
    result: ConnectorProbeResult,
    options: { fromSave?: boolean } = {},
  ) => {
    const fromSave = options.fromSave === true;
    if (result.ok) {
      const tools = result.tools ?? [];
      setProbeResults((prev) => ({ ...prev, [card.key]: tools }));
      setOauthAvailable((prev) => ({ ...prev, [card.key]: false }));
      if (!fromSave) {
        updateCard(card.key, { collapsed: false });
      }
      if (!fromSave) {
        if (tools.length === 0) {
          message.success(
            t("connectors.probeToolsEmpty", "连接正常，但未发现可用工具"),
          );
        } else {
          message.success(t("connectors.customMcp.probeComplete", "连接正常"));
        }
      }
      return;
    }
    setProbeResults((prev) => {
      const next = { ...prev };
      delete next[card.key];
      return next;
    });
    if (result.oauth?.available) {
      setOauthAvailable((prev) => ({ ...prev, [card.key]: true }));
      if (fromSave) {
        updateCard(card.key, { enabled: false, defaultOpen: false });
      } else {
        updateCard(card.key, {
          collapsed: false,
          enabled: false,
          defaultOpen: false,
        });
      }
      if (!fromSave) {
        message.warning(
          t(
            "connectors.customMcp.probeNeedsOAuth",
            "此 MCP 需要 OAuth 授权才能访问",
          ),
        );
      }
      return;
    }
    setOauthAvailable((prev) => ({ ...prev, [card.key]: false }));
    if (!fromSave) {
      message.error(result.error ?? t("connectors.probeFailed", "探测失败"));
    }
  };

  const runProbe = async (
    card: ServerCardState,
    options: { byName?: boolean; fromSave?: boolean } = {},
  ) => {
    const byName = options.byName === true;
    const fromSave = options.fromSave === true;
    setProbingKey(card.key);
    clearProbeResult(card.key);
    try {
      let result: ConnectorProbeResult;
      if (byName || card.oauthConfigured) {
        result = await connectorsApi.testCustomMcp({ name: card.name.trim() });
      } else {
        const map = cardsToServers([card]);
        const server = map[card.name.trim()];
        result = await connectorsApi.testCustomMcp({ server });
      }
      applyProbeResult(card, result, { fromSave });
    } catch (e) {
      console.error(e);
      message.error(
        apiErrorMessage(e, t("connectors.probeFailed", "探测失败"), t),
      );
    } finally {
      setProbingKey(null);
    }
  };

  const resolveServersForSave = (): CustomMcpServers | null => {
    if (mode === "json") {
      try {
        const parsed = JSON.parse(jsonText) as unknown;
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("root must be object");
        }
        setJsonError(null);
        return parsed as CustomMcpServers;
      } catch {
        setJsonError(t("connectors.customMcp.jsonInvalid", "JSON 格式无效"));
        message.error(t("connectors.customMcp.jsonInvalid", "JSON 格式无效"));
        return null;
      }
    }
    try {
      return cardsToServers(cards);
    } catch (e) {
      const code = e instanceof Error ? e.message : "";
      if (code === "duplicate_name") {
        message.warning(
          t("connectors.customMcp.duplicateName", "服务器名称不能重复"),
        );
      } else if (code === "empty_name") {
        message.warning(
          t("connectors.customMcp.emptyName", "请填写服务器名称"),
        );
      } else {
        message.warning(
          apiErrorMessage(
            e,
            t("connectors.customMcp.visualInvalid", "请检查配置后重试"),
            t,
          ),
        );
      }
      return null;
    }
  };

  const handleSave = async () => {
    const servers = resolveServersForSave();
    if (!servers) return;
    setSaving(true);
    try {
      const saved = await connectorsApi.putCustomMcp(servers);
      const nextCards = applySavedServers(saved.servers, cards);
      notifyConnectorsChanged();
      message.success(
        t("connectors.customMcp.saveSuccess", "自定义 MCP 已保存"),
      );
      if (probeOnSave && showProbeSection) {
        for (const card of nextCards) {
          if (card.transport !== "streamable_http" || !card.url.trim()) {
            continue;
          }
          await runProbe(card, { byName: true, fromSave: true });
        }
      }
    } catch (e) {
      console.error(e);
      message.error(
        apiErrorMessage(e, t("connectors.customMcp.saveFailed", "保存失败"), t),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleProbe = async (card: ServerCardState) => {
    try {
      cardsToServers([card]);
    } catch {
      message.warning(
        t("connectors.customMcp.probeNeedConfig", "请先填写完整配置再探测"),
      );
      return;
    }
    await runProbe(card);
  };

  const handleOAuth = async (card: ServerCardState) => {
    const serverName = card.name.trim();
    if (!serverName) {
      message.warning(t("connectors.customMcp.emptyName", "请填写服务器名称"));
      return;
    }
    const popup = window.open("", "octop-oauth", "width=520,height=720");
    if (!popup) {
      message.error(
        t(
          "connectors.oauthPopupBlocked",
          "授权窗口被浏览器拦截，请允许本站弹出窗口后重试",
        ),
      );
      return;
    }

    setAuthorizingKey(card.key);
    let settled = false;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let timeoutTimer: ReturnType<typeof setTimeout> | undefined;
    let stateId = "";

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
        popup.close();
      } catch {
        // ignore
      }
      setAuthorizingKey(null);
      try {
        const { servers } = await connectorsApi.getCustomMcp();
        const nextCards = applySavedServers(servers, cards);
        const refreshed = nextCards.find((c) => c.name.trim() === serverName);
        if (refreshed) {
          await runProbe(refreshed, { byName: true });
        }
        message.success(
          t("connectors.oauthConfigured", "已授权，可直接探测或保存"),
        );
      } catch (e) {
        console.error(e);
        message.error(
          apiErrorMessage(
            e,
            t("connectors.oauthFailed", "获取授权结果失败"),
            t,
          ),
        );
      }
    };

    const claimPending = async () => {
      if (!stateId || settled) return;
      try {
        const pending = await connectorsApi.oauthPending(stateId);
        if (pending.applied || pending.server_name) {
          await finish();
        }
      } catch {
        // keep polling until timeout
      }
    };

    const onMessage = (ev: MessageEvent) => {
      if (ev.data?.type !== "octop:connector-oauth") return;
      if (ev.data.state_id !== stateId) return;
      void claimPending();
    };

    try {
      const servers = resolveServersForSave();
      if (!servers) {
        try {
          popup.close();
        } catch {
          // ignore
        }
        setAuthorizingKey(null);
        return;
      }
      const saved = await connectorsApi.putCustomMcp(servers);
      applySavedServers(saved.servers, cards);
      notifyConnectorsChanged();

      const { authorize_url, state_id } = await connectorsApi.oauthStart(
        { type: "custom_mcp", server_name: serverName },
        window.location.pathname,
      );
      stateId = state_id;
      window.addEventListener("message", onMessage);
      pollTimer = setInterval(() => {
        void claimPending();
      }, 1200);
      timeoutTimer = setTimeout(() => {
        if (settled) return;
        settled = true;
        cleanup();
        setAuthorizingKey(null);
        message.error(
          t("connectors.oauthTimedOut", "授权超时，请重试一键授权"),
        );
      }, 120_000);
      popup.location.replace(authorize_url);
    } catch (e) {
      cleanup();
      setAuthorizingKey(null);
      try {
        popup.close();
      } catch {
        // ignore
      }
      message.error(
        apiErrorMessage(
          e,
          t("connectors.oauthStartFailed", "无法启动 OAuth"),
          t,
        ),
      );
    }
  };

  const transportOptions = useMemo(
    () => [
      { value: "streamable_http", label: "streamable_http" },
      { value: "stdio", label: "stdio" },
    ],
    [],
  );

  const showProbeSection = useMemo(() => {
    if (mode === "visual") {
      return hasHttpProbeTargets(cards);
    }
    try {
      const parsed = JSON.parse(jsonText) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return false;
      }
      return hasHttpProbeTargets(parsed as CustomMcpServers);
    } catch {
      return false;
    }
  }, [mode, cards, jsonText]);

  if (loading) {
    return (
      <div className={styles.loadingState}>
        <Spin />
      </div>
    );
  }

  const saveFooter = (
    <div
      className={`${styles.customMcpFooter}${
        showProbeSection ? "" : ` ${styles.customMcpFooterSaveOnly}`
      }`}
    >
      {showProbeSection ? (
        <div className={styles.customMcpFooterMain}>
          <Checkbox
            checked={probeOnSave}
            onChange={(e) => setProbeOnSave(e.target.checked)}
          >
            {t("connectors.customMcp.probeOnSave", "保存后自动探测连接")}
          </Checkbox>
          <p className={styles.customMcpFooterHint}>
            {t(
              "connectors.customMcp.probeOnSaveHint",
              "将向您填写的 MCP 地址发起请求以验证可用性；若需登录，会引导您完成 OAuth。",
            )}
          </p>
        </div>
      ) : null}
      <Button
        type="primary"
        className={styles.customMcpFooterSave}
        loading={saving}
        onClick={() => void handleSave()}
      >
        {t("common.save")}
      </Button>
    </div>
  );

  return (
    <div className={styles.customMcpTab}>
      <div className={styles.customMcpIntro}>
        <div className={styles.customMcpIntroTitle}>
          {t(
            "connectors.customMcp.introTitle",
            "MCP 服务器配置（JSON 格式）。参考以下格式：",
          )}
        </div>
        <pre className={styles.customMcpExample}>{EXAMPLE_JSON}</pre>
      </div>

      <div className={styles.customMcpToolbar}>
        <Segmented
          value={mode}
          onChange={(value) => handleModeChange(value as EditorMode)}
          options={[
            {
              value: "visual",
              label: t("connectors.customMcp.modeVisual", "可视化"),
            },
            {
              value: "json",
              label: t("connectors.customMcp.modeJson", "</> JSON"),
            },
          ]}
        />
      </div>

      {mode === "json" ? (
        <>
          <div className={styles.customMcpPanel}>
            <div className={styles.customMcpJsonEditor}>
              <Input.TextArea
                value={jsonText}
                onChange={(e) => {
                  setJsonText(e.target.value);
                  setJsonError(null);
                }}
                autoSize={{ minRows: 16, maxRows: 32 }}
                className={styles.customMcpJsonArea}
                spellCheck={false}
              />
              {jsonError ? (
                <div className={styles.customMcpJsonError}>{jsonError}</div>
              ) : null}
            </div>
          </div>
          {saveFooter}
        </>
      ) : (
        <>
          <div className={styles.customMcpPanel}>
            <div className={styles.customMcpAddRow}>
              <button
                type="button"
                className={styles.customMcpAddBtn}
                onClick={() => handleAdd("streamable_http")}
              >
                <Globe size={18} />
                <span>
                  {t("connectors.customMcp.addHttp", "添加 HTTP Server")}
                </span>
                <Plus size={16} />
              </button>
              <button
                type="button"
                className={styles.customMcpAddBtn}
                onClick={() => handleAdd("stdio")}
              >
                <Terminal size={18} />
                <span>
                  {t("connectors.customMcp.addStdio", "添加 Stdio Server")}
                </span>
                <Plus size={16} />
              </button>
            </div>

            <div className={styles.customMcpListSection}>
              <div className={styles.customMcpListTitle}>
                {t("connectors.customMcp.listTitle", "已添加的服务器")}
                {cards.length > 0 ? (
                  <span className={styles.customMcpListCount}>
                    {cards.length}
                  </span>
                ) : null}
              </div>

              {cards.length === 0 ? (
                <div className={styles.customMcpEmpty}>
                  {t(
                    "connectors.customMcp.emptyList",
                    "尚未添加自定义 MCP，点击上方按钮开始配置",
                  )}
                </div>
              ) : (
                <div className={styles.customMcpGrid}>
                  {cards.map((card) => (
                    <CustomMcpServerCard
                      key={card.key}
                      card={card}
                      probing={probingKey === card.key}
                      authorizing={authorizingKey === card.key}
                      oauthAvailable={oauthAvailable[card.key] === true}
                      probeTools={probeResults[card.key]}
                      transportOptions={transportOptions}
                      onUpdate={updateCard}
                      onToggleEnabled={(enabled) => {
                        if (
                          oauthAvailable[card.key] &&
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
                        void persistServerPatch(
                          card,
                          {
                            enabled,
                            ...(enabled ? {} : { default_open: false }),
                          },
                          {
                            enabled,
                            ...(enabled ? {} : { defaultOpen: false }),
                          },
                        );
                      }}
                      onDefaultOpenChange={(defaultOpen) => {
                        void persistServerPatch(
                          card,
                          { default_open: defaultOpen },
                          { defaultOpen },
                        );
                      }}
                      onRemove={() => handleRemove(card.key)}
                      onProbe={() => void handleProbe(card)}
                      onAuthorize={() => void handleOAuth(card)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
          {saveFooter}
        </>
      )}
    </div>
  );
}
