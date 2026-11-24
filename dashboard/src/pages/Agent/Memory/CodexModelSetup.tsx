import { useEffect, useState } from "react";
import { Alert, Button, Form, Input, Select, Space } from "antd";
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

interface Props {
  token: MemoryMcpToken;
  prompt: (token: MemoryMcpToken, choice: string) => string;
  copy: (text: string) => Promise<void>;
}

export default function CodexModelSetup({ token, prompt, copy }: Props) {
  const { t } = useTranslation();
  const [choice, setChoice] = useState("codex");
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
        if (active) setChoice(saved.model ?? "codex");
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
  const text = prompt(token, choice);
  const title = t("memory.mcp.codexPromptLabel", "Codex 接入提示词");
  return (
    <>
      {writable && (
        <Form.Item
          label={t("memory.mcp.extractionSource", "记忆提取模型")}
          extra={t(
            "memory.mcp.modelApplyHint",
            "首次接入或切换提取方式时，请在 Codex 执行下方提示词。更换已选的 Octop 模型会在下次提取时生效。",
          )}
        >
          <Select
            aria-label={t("memory.mcp.extractionSource", "记忆提取模型")}
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
                  "当前 Codex 对话模型（额外一轮）",
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
        </Form.Item>
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
      <Space.Compact style={{ width: "100%" }}>
        <Input.TextArea
          aria-label={title}
          readOnly
          autoSize={{ minRows: 6, maxRows: 11 }}
          value={busy || loadError ? "" : text}
          style={{ fontFamily: "monospace", fontSize: 12 }}
        />
        <Button disabled={busy || loadError} onClick={() => void copy(text)}>
          {t("memory.mcp.copyPrompt", "复制提示词")}
        </Button>
      </Space.Compact>
    </>
  );
}
