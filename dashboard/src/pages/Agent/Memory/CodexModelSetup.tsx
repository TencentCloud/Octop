import { useEffect, useState } from "react";
import { Alert, Button, Input, Select, Tag, Typography } from "antd";
import { ArrowRight, Copy, RefreshCw, Terminal } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  memoryMcpApi,
  type MemoryMcpToken,
  type CodexStatus,
} from "../../../api/modules/memoryMcp";
import { providerApi } from "../../../api/modules/provider";
import {
  modelOptionLabel,
  modelOptionValue,
} from "../../../utils/modelOptions";
import { message } from "@/utils/antdMessage";

import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";

import styles from "./MemorySettings.module.less";

interface Props {
  view: "model" | "setup" | "onboarding";
  onConfigure?: () => void;
  token: MemoryMcpToken;
  prompt: (token: MemoryMcpToken, choice: string) => string;
  copy: (text: string) => Promise<void>;
}

export default function CodexModelSetup({
  token,
  prompt,
  copy,
  view,
  onConfigure,
}: Props) {
  const { t } = useTranslation();
  const [choice, setChoice] = useState("codex");
  const [savedChoice, setSavedChoice] = useState("codex");
  const [publishedAt, setPublishedAt] = useState<string | null>(null);
  const timeZone = useServerTimezone();
  const [modeSince, setModeSince] = useState<string | null>(null);
  const [status, setStatus] = useState<CodexStatus | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [readingStatus, setReadingStatus] = useState(false);
  const [statusRequest, refreshStatus] = useState(0);
  const [models, setModels] = useState<{ label: string; value: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [modelsError, setModelsError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const writable = !!token.scopes?.includes("write");
  const space = token.space_id;
  useEffect(() => {
    if (!writable || !space) return;
    let active = true;
    setBusy(true);
    setLoadError(false);
    setModelsError(false);
    providerApi
      .listResolvedModels()
      .then((rows) => {
        if (active)
          setModels(
            rows.map((row) => ({
              label: modelOptionLabel(row),
              value: modelOptionValue(row),
            })),
          );
      })
      .catch(() => {
        if (active) setModelsError(true);
      });
    memoryMcpApi
      .getCodexModel(token.token_id, space)
      .then((saved) => {
        if (!active) return;
        const value = saved.model ?? saved.mode ?? "codex";
        setChoice(value);
        setSavedChoice(value);
        setPublishedAt(saved.published_at ?? null);
        setModeSince(saved.mode_since ?? null);
      })
      .catch(() => {
        if (active) setLoadError(true);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [space, token.token_id, writable, attempt]);

  useEffect(() => {
    if (view !== "model" || !writable || !space) return;
    let active = true;
    setReadingStatus(true);
    memoryMcpApi
      .getCodexStatus(token.token_id, space)
      .then((result) => {
        if (active) {
          setStatus(result);
          setStatusError(false);
        }
      })
      .catch(() => {
        if (active) {
          setStatus(null);
          setStatusError(true);
        }
      })
      .finally(() => {
        if (active) setReadingStatus(false);
      });
    return () => {
      active = false;
    };
  }, [view, token.token_id, space, writable, statusRequest]);

  const save = async (next: string, publish = false) => {
    if (!space) {
      // Older create responses can omit the space; keep their local setup choices usable.
      if (view === "onboarding" && !next.includes("/")) setChoice(next);
      return;
    }
    setBusy(true);
    try {
      const saved = await memoryMcpApi.setCodexModel(
        token.token_id,
        space,
        next.includes("/") ? next : null,
        next === "server" ? "server" : undefined,
        publish,
      );
      setChoice(next);
      setSavedChoice(next);
      setPublishedAt(saved.published_at ?? null);
      setModeSince(saved.mode_since ?? null);
      refreshStatus((n) => n + 1);
    } catch {
      message.error(t("memory.mcp.modelSaveError", "未能保存提取模型"));
    } finally {
      setBusy(false);
    }
  };
  const desiredMode = savedChoice.includes("/") ? "octop" : savedChoice;
  const dirty = choice !== savedChoice;
  const observed = status?.observed;
  const acknowledged =
    !!publishedAt && status?.acknowledgement?.revision === publishedAt;
  const confirmed = publishedAt
    ? acknowledged
    : observed?.mode === desiredMode &&
      (!modeSince || Date.parse(observed.timestamp) >= Date.parse(modeSince));
  useEffect(() => {
    if (view !== "model" || !publishedAt || acknowledged || readingStatus)
      return;
    const timer = window.setTimeout(() => refreshStatus((n) => n + 1), 5000);
    return () => window.clearTimeout(timer);
  }, [view, publishedAt, acknowledged, readingStatus]);
  const modeLabel = (mode: string) =>
    mode === "codex"
      ? t("memory.mcp.modeCodex", "Codex 会话复核")
      : mode === "server"
      ? t("memory.mcp.modeServer", "Memory 服务端提取")
      : t("memory.mcp.modeOctop", "Octop 委托复核");
  const title = t("memory.mcp.codexPromptLabel", "Codex 接入提示词");
  const text =
    view === "model" || busy || loadError ? "" : prompt(token, choice);

  return (
    <div className={styles.codexSettings}>
      {writable && view !== "setup" && (
        <div className={styles.codexField}>
          {view === "model" && (
            <Typography.Text type="secondary" className={styles.codexToken}>
              <Terminal size={14} aria-hidden />
              {token.name}
            </Typography.Text>
          )}
          <Typography.Text>
            {t("memory.mcp.desiredModel", "期望的提取模型")}
          </Typography.Text>
          <Select
            aria-label={t("memory.mcp.extractionSource", "记忆提取模型")}
            className={styles.codexSelect}
            showSearch
            optionFilterProp="label"
            value={choice}
            loading={busy}
            disabled={busy || loadError}
            onChange={(value) =>
              view === "model" ? setChoice(value) : void save(value)
            }
            options={[
              {
                value: "codex",
                label: t(
                  "memory.mcp.codexExtractOption",
                  "跟随当前 Codex 会话",
                ),
              },
              ...(models.length
                ? [
                    {
                      label: t("memory.mcp.octopModels", "Octop 模型"),
                      options: models,
                    },
                  ]
                : []),
              {
                value: "server",
                label: t(
                  "memory.mcp.serverExtractOption",
                  "Memory 服务配置的模型",
                ),
              },
            ]}
          />
          {view === "model" && (
            <>
              <Typography.Text type="secondary">
                {t(
                  "memory.mcp.applyScope",
                  "更换提取模型后，先点击「应用到终端」。已启用面板同步的 Codex 会在下一轮对话结束时自动应用新配置。",
                )}
              </Typography.Text>
              <Button
                type="primary"
                loading={busy}
                disabled={loadError || !space || (!!publishedAt && !dirty)}
                onClick={() => void save(choice, true)}
              >
                {t("memory.mcp.publishMode", "应用到终端")}
              </Button>
            </>
          )}
          {view === "model" && !busy && !loadError && (
            <section
              className={styles.codexStatus}
              aria-label={t("memory.mcp.terminalStatus", "终端应用状态")}
            >
              <div className={styles.codexStatusHeading}>
                <Typography.Text strong>
                  {t("memory.mcp.terminalStatus", "终端应用状态")}
                </Typography.Text>
                <Button
                  type="text"
                  size="small"
                  aria-label={t("memory.mcp.refreshStatus", "刷新终端状态")}
                  icon={<RefreshCw size={14} />}
                  loading={readingStatus}
                  onClick={() => refreshStatus((n) => n + 1)}
                />
              </div>
              <div role="status">
                <Tag
                  color={
                    confirmed && !dirty && !statusError
                      ? "green"
                      : statusError
                      ? undefined
                      : "orange"
                  }
                >
                  {statusError
                    ? t("memory.mcp.statusUnavailable", "状态暂不可用")
                    : readingStatus && !status
                    ? t("common.loading", "加载中")
                    : dirty
                    ? t("memory.mcp.unpublishedChoice", "所选配置尚未应用")
                    : confirmed
                    ? t("memory.mcp.appliedMode", "终端已确认")
                    : !publishedAt
                    ? t("memory.mcp.unpublishedChoice", "所选配置尚未应用")
                    : t("memory.mcp.pendingMode", "等待终端确认")}
                </Tag>
                {observed && (
                  <span>
                    {t("memory.mcp.reportedMode", "最近运行方式：{{mode}}", {
                      mode: modeLabel(observed.mode),
                    })}
                  </span>
                )}
              </div>
              {observed && (
                <Typography.Text type="secondary">
                  {t("memory.mcp.lastModeReport", "最近上报 {{time}}", {
                    time: formatServerIsoDateTime(observed.timestamp, timeZone),
                  })}
                </Typography.Text>
              )}
              <div className={styles.codexLastRun}>
                <Typography.Text strong>
                  {t("memory.mcp.lastTerminalRun", "最近实际提取模型")}
                </Typography.Text>
                {status?.last_run ? (
                  <>
                    <Typography.Text>
                      {status.last_run.model || modeLabel(status.last_run.mode)}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      {formatServerIsoDateTime(
                        status.last_run.timestamp,
                        timeZone,
                      )}
                    </Typography.Text>
                  </>
                ) : (
                  <Typography.Text type="secondary">
                    {statusError
                      ? t("memory.mcp.statusUnavailable", "状态暂不可用")
                      : readingStatus
                      ? t("common.loading", "加载中")
                      : t("memory.mcp.noTerminalRun", "暂无该凭据的执行记录")}
                  </Typography.Text>
                )}
              </div>
            </section>
          )}
          {view === "model" && (
            <Typography.Text type="secondary">
              {t(
                "memory.mcp.manualSetupHint",
                "如果本机尚未启用面板同步，发布后请重新点击「配置本机 Codex」，复制指令并在本机 Codex 对话中执行。",
              )}
            </Typography.Text>
          )}
        </div>
      )}
      {(loadError || modelsError) && (
        <Alert
          type="warning"
          showIcon
          message={t("memory.mcp.modelLoadError", "未能加载模型设置")}
          action={
            <Button onClick={() => setAttempt((n) => n + 1)}>
              {t("common.retry", "重试")}
            </Button>
          }
        />
      )}
      {view === "model" ? (
        <Button
          type="link"
          className={styles.codexConfigure}
          onClick={onConfigure}
          disabled={busy || loadError || dirty}
        >
          {t("memory.mcp.configureCodex", "配置本机 Codex")}{" "}
          <ArrowRight size={14} aria-hidden />
        </Button>
      ) : (
        <>
          <Typography.Text type="secondary">
            {t(
              "memory.mcp.pasteInCodex",
              "复制指令，在要接入的 Codex 对话中执行。",
            )}
          </Typography.Text>
          <Button
            type="primary"
            className={styles.codexCopy}
            icon={<Copy size={15} />}
            disabled={!text}
            onClick={() => void copy(text)}
          >
            {t("memory.mcp.copyPrompt", "复制提示词")}
          </Button>
          <details className={styles.codexInstructions}>
            <summary>
              {t("memory.mcp.viewInstructions", "查看完整指令")}
            </summary>
            <Input.TextArea
              aria-label={title}
              readOnly
              autoSize={{ minRows: 4, maxRows: 8 }}
              value={text}
            />
          </details>
        </>
      )}
    </div>
  );
}
