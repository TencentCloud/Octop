import { useEffect, useState } from "react";
import { Alert, Button, Input, Select, Typography } from "antd";
import { ArrowRight, Copy, Terminal } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  memoryMcpApi,
  type MemoryMcpToken,
} from "../../../api/modules/memoryMcp";
import { providerApi } from "../../../api/modules/provider";
import {
  modelOptionLabel,
  modelOptionValue,
} from "../../../utils/modelOptions";
import { message } from "@/utils/antdMessage";

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
  const [initialChoice, setInitialChoice] = useState("codex");
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
        setChoice(saved.model ?? "codex");
        setInitialChoice(saved.model ?? "codex");
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

  const select = async (next: string) => {
    if (space && (next.includes("/") || choice.includes("/"))) {
      setBusy(true);
      try {
        await memoryMcpApi.setCodexModel(
          token.token_id,
          space,
          next.includes("/") ? next : null,
        );
      } catch {
        message.error(t("memory.mcp.modelSaveError", "未能保存提取模型"));
        return;
      } finally {
        setBusy(false);
      }
    }
    setChoice(next);
  };
  const mode = (value: string) => (value.includes("/") ? "octop" : value);
  const needsSetup = mode(initialChoice) !== mode(choice);
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
          <Select
            aria-label={t("memory.mcp.extractionSource", "记忆提取模型")}
            className={styles.codexSelect}
            showSearch
            optionFilterProp="label"
            value={choice}
            loading={busy}
            disabled={busy || loadError}
            onChange={(value) => void select(value)}
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
          {view === "model" && !busy && !loadError && (
            <Typography.Text type="secondary" role="status">
              {needsSetup
                ? t(
                    "memory.mcp.modelSwitchHint",
                    "切换提取方式后，请在本机 Codex 应用配置。",
                  )
                : choice.includes("/")
                ? t(
                    "memory.mcp.octopModelHint",
                    "更换 Octop 模型后，下次提取生效。",
                  )
                : t(
                    "memory.mcp.codexModelHint",
                    "每轮结束后，由当前会话模型额外复核一次。",
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
          disabled={busy || loadError}
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
