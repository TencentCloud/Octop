import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Input, Segmented, Spin, message } from "antd";
import { Globe, Plus, Terminal } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  connectorsApi,
  type CustomMcpServerSpec,
  type CustomMcpServers,
  type CustomMcpTransport,
} from "../../../api/modules/connectors";
import { apiErrorMessage } from "../../../utils/apiError";
import { CustomMcpServerCard } from "./CustomMcpServerCard";
import {
  EXAMPLE_JSON,
  cardsToServers,
  newCard,
  notifyConnectorsChanged,
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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { servers } = await connectorsApi.getCustomMcp();
      const nextCards = serversToCards(servers);
      setCards(nextCards);
      setProbeResults({});
      setJsonText(JSON.stringify(servers, null, 2));
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

  const handleRemove = (key: string) => {
    setCards((prev) => {
      const next = prev.filter((card) => card.key !== key);
      syncJsonFromCards(next);
      return next;
    });
    setProbeResults((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const clearProbeResult = (key: string) => {
    setProbeResults((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
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
      const nextCards = serversToCards(saved.servers);
      setCards(nextCards);
      setJsonText(JSON.stringify(saved.servers, null, 2));
      notifyConnectorsChanged();
      message.success(
        t("connectors.customMcp.saveSuccess", "自定义 MCP 已保存"),
      );
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
    let server: CustomMcpServerSpec;
    try {
      const map = cardsToServers([card]);
      server = map[card.name.trim()];
    } catch {
      message.warning(
        t("connectors.customMcp.probeNeedConfig", "请先填写完整配置再探测"),
      );
      return;
    }
    setProbingKey(card.key);
    clearProbeResult(card.key);
    try {
      const result = await connectorsApi.testCustomMcp({ server });
      if (result.ok) {
        const tools = result.tools ?? [];
        setProbeResults((prev) => ({ ...prev, [card.key]: tools }));
        updateCard(card.key, { collapsed: false });
        if (tools.length === 0) {
          message.success(
            t("connectors.probeToolsEmpty", "连接正常，但未发现可用工具"),
          );
        }
      } else {
        message.error(result.error ?? t("connectors.probeFailed", "探测失败"));
      }
    } catch (e) {
      console.error(e);
      message.error(
        apiErrorMessage(e, t("connectors.probeFailed", "探测失败"), t),
      );
    } finally {
      setProbingKey(null);
    }
  };

  const transportOptions = useMemo(
    () => [
      { value: "streamable_http", label: "streamable_http" },
      { value: "stdio", label: "stdio" },
    ],
    [],
  );

  if (loading) {
    return (
      <div className={styles.loadingState}>
        <Spin />
      </div>
    );
  }

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
      ) : (
        <>
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
                    probeTools={probeResults[card.key]}
                    transportOptions={transportOptions}
                    onUpdate={updateCard}
                    onToggleEnabled={(enabled) =>
                      updateCard(card.key, { enabled })
                    }
                    onRemove={() => handleRemove(card.key)}
                    onProbe={() => void handleProbe(card)}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <div className={styles.customMcpFooter}>
        <Button
          type="primary"
          loading={saving}
          onClick={() => void handleSave()}
        >
          {t("common.save")}
        </Button>
      </div>
    </div>
  );
}
