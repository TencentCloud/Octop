/**
 * ModelListEditor — edit the draft models list for a provider.
 *
 * Mutations stay local until the parent modal saves (PATCH full models array).
 * Connectivity tests still hit the live provider endpoint.
 */
import { useState } from "react";
import {
  App,
  Button,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Tooltip,
} from "antd";

import {
  Check,
  ChevronDown,
  ChevronUp,
  Download,
  Pencil,
  Plus,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../../../api/request";
import type { ProviderRow, ProviderModel } from "../../useProviders";
import { isEmbeddingModel } from "../../useProviders";
import { isOnnxProviderRow } from "../../presetUtils";
import { ModelMetaTags } from "../../modelMeta";
import { buildProviderModelEntry } from "../../modelEntry";
import styles from "../../index.module.less";

export interface LocalModelDownloadControl {
  /** Model ids already present on disk / in the local runtime. */
  downloadedIds: ReadonlySet<string> | readonly string[];
  /** Model ids currently downloading. */
  downloadingIds?: ReadonlySet<string> | readonly string[];
  onDownload: (modelId: string) => void;
  /** When true, enable switch is locked until the model is downloaded. */
  requireDownloadToEnable?: boolean;
}

interface ModelListEditorProps {
  provider: ProviderRow;
  models: ProviderModel[];
  onModelsChange: (models: ProviderModel[]) => void;
  /** API path prefix for test. Defaults to "/providers". */
  apiPrefix?: string;
  canTest?: boolean;
  localDownload?: LocalModelDownloadControl;
  onTestModel?: (
    modelId: string,
    modelName: string,
  ) => Promise<{ ok: boolean; latency_ms?: number; error?: string }>;
}

const INPUT_TYPE_OPTIONS = [
  { value: "text", label: "inputTypeText" as const },
  { value: "image", label: "inputTypeImage" as const },
  { value: "audio", label: "inputTypeAudio" as const },
];

export function ModelListEditor({
  provider,
  models,
  onModelsChange,
  apiPrefix = "/providers",
  canTest,
  localDownload,
  onTestModel,
}: ModelListEditorProps) {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();
  const downloadedSet = (() => {
    if (!localDownload) return null;
    const raw = localDownload.downloadedIds;
    return raw instanceof Set ? raw : new Set(raw);
  })();
  const downloadingSet = (() => {
    if (!localDownload?.downloadingIds) return new Set<string>();
    const raw = localDownload.downloadingIds;
    return raw instanceof Set ? raw : new Set(raw);
  })();
  const requireDownload = !!localDownload?.requireDownloadToEnable;
  const [adding, setAdding] = useState(false);
  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [testingIds, setTestingIds] = useState<Set<string>>(new Set());
  const [testResults, setTestResults] = useState<
    Map<string, "success" | "failure">
  >(new Map());
  const [testingForm, setTestingForm] = useState(false);
  const [form] = Form.useForm();
  const isOnnx = isOnnxProviderRow(provider);
  const embeddingValue = Form.useWatch("embedding", form);
  const embeddingOn = isOnnx || embeddingValue === true;

  const handleToggleEnabled = (
    modelId: string,
    _modelName: string,
    enabled: boolean,
  ) => {
    if (
      enabled &&
      requireDownload &&
      downloadedSet &&
      !downloadedSet.has(modelId)
    ) {
      message.warning(t("models.downloadBeforeEnable"));
      return;
    }
    onModelsChange(
      models.map((m) => (m.id === modelId ? { ...m, enabled } : m)),
    );
  };

  const handleRemoveModel = (modelId: string, modelName: string) => {
    modal.confirm({
      title: t("models.removeModel"),
      content: t("models.removeModelConfirm", {
        name: modelName,
        provider: provider.name,
      }),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: () => {
        onModelsChange(models.filter((m) => m.id !== modelId));
        if (editingModelId === modelId) resetForm();
        message.success(t("models.modelRemoved", { name: modelName }));
      },
    });
  };

  const runTest = async (
    modelId: string,
    modelName: string,
    embedding?: boolean,
  ): Promise<{ ok: boolean; latency_ms?: number; error?: string }> => {
    if (onTestModel) {
      return onTestModel(modelId, modelName);
    }
    const isEmbedding =
      embedding ??
      (isOnnx || isEmbeddingModel(models.find((m) => m.id === modelId)));
    return request<{
      ok: boolean;
      latency_ms?: number;
      error?: string;
    }>(`${apiPrefix}/${provider.id}/test`, {
      method: "POST",
      body: JSON.stringify({ model_id: modelId, embedding: isEmbedding }),
    });
  };

  const handleTestModel = async (modelId: string, modelName: string) => {
    setTestingIds((prev) => new Set(prev).add(modelId));
    try {
      const result = await runTest(modelId, modelName);
      if (result.ok) {
        message.success(
          t("models.testSuccess", {
            name: modelName,
            time: result.latency_ms ?? 0,
          }),
        );
        setTestResults((prev) => new Map(prev).set(modelId, "success"));
      } else {
        message.error(
          t("models.testFailed", { error: result.error ?? "unknown" }),
        );
        setTestResults((prev) => new Map(prev).set(modelId, "failure"));
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      message.error(t("models.testFailed", { error: msg }));
      setTestResults((prev) => new Map(prev).set(modelId, "failure"));
    } finally {
      setTestingIds((prev) => {
        const next = new Set(prev);
        next.delete(modelId);
        return next;
      });
      setTimeout(() => {
        setTestResults((prev) => {
          const next = new Map(prev);
          next.delete(modelId);
          return next;
        });
      }, 2000);
    }
  };

  const handleTestFormModel = async () => {
    const modelId = (form.getFieldValue("id") as string | undefined)?.trim();
    if (!modelId) {
      message.warning(t("models.modelIdLabel"));
      return;
    }
    if (!(canTest ?? !!provider.api_key)) {
      message.warning(t("models.testRequiresAuth"));
      return;
    }
    setTestingForm(true);
    try {
      const result = await runTest(modelId, modelId, embeddingOn);
      const modelName =
        (form.getFieldValue("name") as string | undefined)?.trim() || modelId;
      if (result.ok) {
        message.success(
          t("models.testSuccess", {
            name: modelName,
            time: result.latency_ms ?? 0,
          }),
        );
      } else {
        message.error(
          t("models.testFailed", { error: result.error ?? "unknown" }),
        );
      }
    } catch (err) {
      message.error(t("models.testFailed", { error: String(err) }));
    } finally {
      setTestingForm(false);
    }
  };

  const handleAddModel = async () => {
    try {
      const values = await form.validateFields();
      const entry = buildProviderModelEntry(values as Record<string, unknown>, {
        isOnnx,
      });
      if (models.some((m) => m.id === entry.id)) {
        message.error(t("models.initialModelDuplicate", { name: entry.id }));
        return;
      }
      if (requireDownload) {
        entry.enabled = false;
      }
      onModelsChange([...models, entry]);
      message.success(t("models.modelAdded", { name: entry.name }));
      resetForm();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
    }
  };

  const handleEditModel = async () => {
    if (!editingModelId) return;
    try {
      const values = await form.validateFields();
      const existing = models.find((m) => m.id === editingModelId);
      const entry = buildProviderModelEntry(values as Record<string, unknown>, {
        existing,
        isOnnx,
      });
      if (existing) {
        entry.enabled = existing.enabled;
      }
      onModelsChange(models.map((m) => (m.id === editingModelId ? entry : m)));
      message.success(t("models.modelUpdated", { name: entry.name }));
      resetForm();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
    }
  };

  const startEditing = (model: ProviderModel & Record<string, unknown>) => {
    setAdding(false);
    setEditingModelId(model.id);
    form.setFieldsValue({
      id: model.id,
      name: model.name,
      context_window:
        (model as Record<string, unknown>).context_window ?? undefined,
      max_tokens: model.max_tokens ?? model.max_output_tokens ?? undefined,
      reasoning: (model as Record<string, unknown>).reasoning ?? undefined,
      reasoning_toggle: model.reasoning_config?.toggle ?? true,
      reasoning_efforts: model.reasoning_config?.efforts ?? [],
      reasoning_default_mode: model.reasoning_config?.default_mode ?? "auto",
      reasoning_default_effort:
        model.reasoning_config?.default_effort ?? undefined,
      reasoning_effort_type: model.reasoning_config?.effort_type ?? "enum",
      reasoning_adapter: model.reasoning_config?.adapter ?? "thinking",
      input: model.input ?? ["text"],
      embedding: Boolean(model.embedding || model.task === "embedding"),
    });
    const hasAdvanced =
      (model as Record<string, unknown>).context_window != null ||
      (model as Record<string, unknown>).max_tokens != null ||
      (model as Record<string, unknown>).max_output_tokens != null ||
      (model as Record<string, unknown>).reasoning != null;
    setShowAdvanced(hasAdvanced);
  };

  const startAdding = () => {
    setEditingModelId(null);
    form.resetFields();
    setAdding(true);
    setShowAdvanced(false);
  };

  const resetForm = () => {
    setAdding(false);
    setEditingModelId(null);
    setShowAdvanced(false);
    form.resetFields();
  };

  const isEditing = editingModelId !== null;
  const isFormVisible = adding || isEditing;
  const hasApiKey = canTest ?? !!provider.api_key;

  return (
    <div>
      <div className={styles.modelList}>
        {models.length === 0 ? (
          <div className={styles.modelListEmpty}>{t("models.noModels")}</div>
        ) : (
          models.map((m) => {
            const isCurrentEditing = editingModelId === m.id;
            const isEnabled = m.enabled !== false;
            const isTesting = testingIds.has(m.id);
            const isDownloaded = downloadedSet ? downloadedSet.has(m.id) : true;
            const isDownloading = downloadingSet.has(m.id);
            const enableLocked = requireDownload && !isDownloaded;
            return (
              <div
                key={m.id}
                className={`${styles.modelListItem}${
                  isCurrentEditing ? ` ${styles.modelListItemEditing}` : ""
                }${!isEnabled ? ` ${styles.modelListItemDisabled}` : ""}`}
              >
                <Tooltip
                  title={
                    enableLocked ? t("models.downloadBeforeEnable") : undefined
                  }
                >
                  <Switch
                    size="small"
                    checked={isEnabled && !enableLocked}
                    disabled={enableLocked}
                    onChange={(checked) =>
                      handleToggleEnabled(m.id, m.name, checked)
                    }
                    className={styles.modelToggle}
                  />
                </Tooltip>
                <div className={styles.modelListItemInfo}>
                  <span className={styles.modelListItemName}>{m.name}</span>
                  {m.name !== m.id && (
                    <span className={styles.modelListItemId}>{m.id}</span>
                  )}
                  {localDownload && (
                    <span className={styles.modelListItemId}>
                      {isDownloaded
                        ? t("models.localModelDownloaded")
                        : t("models.notDownloaded")}
                    </span>
                  )}
                  {(m.embedding || m.task === "embedding") && (
                    <span className={styles.modelListItemId}>
                      {t("models.embeddingOnlyTag")}
                    </span>
                  )}
                  {m.embedding || m.task === "embedding" ? null : (
                    <ModelMetaTags
                      includeText
                      input={m.input}
                      context_window={m.context_window}
                      max_tokens={m.max_tokens ?? m.max_output_tokens}
                      reasoning={m.reasoning}
                    />
                  )}
                </div>
                <div className={styles.modelListItemActions}>
                  {localDownload && !isDownloaded && (
                    <Button
                      type="text"
                      size="small"
                      icon={<Download size={14} />}
                      loading={isDownloading}
                      onClick={() => localDownload.onDownload(m.id)}
                      title={t("models.localDownloadModel")}
                      style={{ marginRight: 4 }}
                    />
                  )}
                  {hasApiKey &&
                    (isTesting ? (
                      <Button
                        type="text"
                        size="small"
                        loading
                        style={{ marginRight: 4 }}
                      />
                    ) : testResults.get(m.id) === "success" ? (
                      <Check
                        size={14}
                        style={{
                          color: "#52c41a",
                          marginRight: 8,
                        }}
                      />
                    ) : testResults.get(m.id) === "failure" ? (
                      <X
                        size={14}
                        style={{
                          color: "#ff4d4f",
                          marginRight: 8,
                        }}
                      />
                    ) : (
                      <Button
                        type="text"
                        size="small"
                        icon={<Zap size={14} />}
                        onClick={() => handleTestModel(m.id, m.name)}
                        title={t("models.testConnection")}
                        style={{ marginRight: 4 }}
                      />
                    ))}
                  <Button
                    type="text"
                    size="small"
                    icon={<Pencil size={14} />}
                    onClick={() =>
                      startEditing(m as ProviderModel & Record<string, unknown>)
                    }
                    disabled={isCurrentEditing}
                  />
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<Trash2 size={14} />}
                    onClick={() => handleRemoveModel(m.id, m.name)}
                  />
                </div>
              </div>
            );
          })
        )}
      </div>

      {isFormVisible ? (
        <div className={styles.modelAddForm}>
          <Form form={form} layout="vertical" style={{ marginBottom: 0 }}>
            <Form.Item
              name="id"
              label={t("models.modelIdLabel")}
              rules={[{ required: true, message: t("models.modelIdLabel") }]}
              style={{ marginBottom: 12 }}
            >
              <Input
                placeholder={t("models.modelIdPlaceholder")}
                disabled={isEditing}
              />
            </Form.Item>
            <Form.Item
              name="name"
              label={t("models.modelNameLabel")}
              style={{ marginBottom: 12 }}
            >
              <Input placeholder={t("models.modelNamePlaceholder")} />
            </Form.Item>

            {isOnnx ? null : (
              <Form.Item
                name="embedding"
                label={t("models.embeddingModel")}
                extra={t("models.embeddingModelHint")}
                valuePropName="checked"
                initialValue={false}
                style={{ marginBottom: 12 }}
              >
                <Switch size="small" />
              </Form.Item>
            )}

            {embeddingOn ? null : (
              <>
                <Form.Item
                  name="input"
                  label={t("models.inputTypes")}
                  initialValue={["text"]}
                  style={{ marginBottom: 12 }}
                >
                  <Select
                    mode="multiple"
                    allowClear
                    placeholder={t("models.inputTypes")}
                    options={INPUT_TYPE_OPTIONS.map((opt) => ({
                      value: opt.value,
                      label: t(`models.${opt.label}`),
                    }))}
                  />
                </Form.Item>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    marginBottom: showAdvanced ? 8 : 12,
                  }}
                >
                  <Button
                    type="link"
                    size="small"
                    style={{ padding: 0 }}
                    icon={
                      showAdvanced ? (
                        <ChevronUp size={14} />
                      ) : (
                        <ChevronDown size={14} />
                      )
                    }
                    onClick={() => setShowAdvanced(!showAdvanced)}
                  >
                    {showAdvanced
                      ? t("models.hideAdvanced")
                      : t("models.showAdvanced")}
                  </Button>
                </div>

                {showAdvanced && (
                  <div
                    style={{
                      background:
                        "var(--ant-color-fill-quaternary, rgba(0,0,0,0.02))",
                      borderRadius: 6,
                      padding: "12px 12px 4px",
                      marginBottom: 12,
                    }}
                  >
                    <div style={{ display: "flex", gap: 12 }}>
                      <Form.Item
                        name="context_window"
                        label={t("models.contextWindow")}
                        style={{ flex: 1, marginBottom: 10 }}
                      >
                        <InputNumber
                          min={0}
                          style={{ width: "100%" }}
                          placeholder={t("models.contextWindowPlaceholder")}
                        />
                      </Form.Item>
                      <Form.Item
                        name="max_tokens"
                        label={t("models.maxTokens")}
                        style={{ flex: 1, marginBottom: 10 }}
                      >
                        <InputNumber
                          min={0}
                          style={{ width: "100%" }}
                          placeholder={t("models.maxTokensPlaceholder")}
                        />
                      </Form.Item>
                    </div>
                    <Form.Item
                      name="reasoning"
                      label={t("models.reasoning")}
                      valuePropName="checked"
                      style={{ marginBottom: 10 }}
                    >
                      <Switch size="small" />
                    </Form.Item>
                    <Form.Item noStyle shouldUpdate>
                      {({ getFieldValue }) =>
                        getFieldValue("reasoning") ? (
                          <>
                            <div style={{ display: "flex", gap: 12 }}>
                              <Form.Item
                                name="reasoning_toggle"
                                label={t("models.reasoningToggle", "允许开关")}
                                valuePropName="checked"
                                initialValue
                                style={{ flex: 1, marginBottom: 10 }}
                              >
                                <Switch size="small" />
                              </Form.Item>
                              <Form.Item
                                name="reasoning_default_mode"
                                label={t("models.reasoningDefault", "默认思考")}
                                initialValue="auto"
                                style={{ flex: 1, marginBottom: 10 }}
                              >
                                <Select
                                  options={[
                                    {
                                      value: "auto",
                                      label: t("chat.reasoningAuto", "自动"),
                                    },
                                    {
                                      value: "enabled",
                                      label: t("chat.reasoningEnabled", "开启"),
                                    },
                                    {
                                      value: "disabled",
                                      label: t(
                                        "chat.reasoningDisabled",
                                        "关闭",
                                      ),
                                    },
                                  ]}
                                />
                              </Form.Item>
                            </div>
                            <Form.Item
                              name="reasoning_efforts"
                              label={t(
                                "models.reasoningEfforts",
                                "支持的思考强度",
                              )}
                              style={{ marginBottom: 10 }}
                            >
                              <Select
                                mode="tags"
                                tokenSeparators={[","]}
                                placeholder="low, medium, high, max, xhigh"
                              />
                            </Form.Item>
                            <div style={{ display: "flex", gap: 12 }}>
                              <Form.Item
                                name="reasoning_default_effort"
                                label={t(
                                  "models.reasoningDefaultEffort",
                                  "默认强度",
                                )}
                                style={{ flex: 1, marginBottom: 10 }}
                              >
                                <Input placeholder="high" />
                              </Form.Item>
                              <Form.Item
                                name="reasoning_effort_type"
                                label={t(
                                  "models.reasoningEffortType",
                                  "强度类型",
                                )}
                                initialValue="enum"
                                style={{ flex: 1, marginBottom: 10 }}
                              >
                                <Select
                                  options={[
                                    {
                                      value: "enum",
                                      label: t(
                                        "models.reasoningEffortEnum",
                                        "强度档位",
                                      ),
                                    },
                                    {
                                      value: "token_budget",
                                      label: t(
                                        "models.reasoningEffortBudget",
                                        "Token 预算",
                                      ),
                                    },
                                  ]}
                                />
                              </Form.Item>
                            </div>
                            <Form.Item
                              name="reasoning_adapter"
                              label={t("models.reasoningAdapter", "推理协议")}
                              initialValue="thinking"
                              style={{ marginBottom: 10 }}
                            >
                              <Select
                                options={[
                                  {
                                    value: "status_only",
                                    label: t(
                                      "models.reasoningAdapterStatusOnly",
                                      "仅标记（始终推理）",
                                    ),
                                  },
                                  {
                                    value: "openai_reasoning_effort",
                                    label: t(
                                      "models.reasoningAdapterOpenAI",
                                      "OpenAI / Gemini / Groq",
                                    ),
                                  },
                                  {
                                    value: "anthropic_adaptive",
                                    label: t(
                                      "models.reasoningAdapterAnthropicAdaptive",
                                      "Anthropic Adaptive",
                                    ),
                                  },
                                  {
                                    value: "anthropic_budget",
                                    label: t(
                                      "models.reasoningAdapterAnthropicBudget",
                                      "Anthropic Token Budget",
                                    ),
                                  },
                                  {
                                    value: "thinking",
                                    label: t(
                                      "models.reasoningAdapterThinking",
                                      "DeepSeek / GLM / Kimi",
                                    ),
                                  },
                                  {
                                    value: "thinking_nested_effort",
                                    label: t(
                                      "models.reasoningAdapterNestedEffort",
                                      "TokenHub 嵌套强度",
                                    ),
                                  },
                                  {
                                    value: "dashscope",
                                    label: t(
                                      "models.reasoningAdapterDashScope",
                                      "DashScope / 阿里云",
                                    ),
                                  },
                                  {
                                    value: "openrouter",
                                    label: t(
                                      "models.reasoningAdapterOpenRouter",
                                      "OpenRouter",
                                    ),
                                  },
                                ]}
                              />
                            </Form.Item>
                          </>
                        ) : null
                      }
                    </Form.Item>
                  </div>
                )}
              </>
            )}

            <div
              style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}
            >
              {hasApiKey && (
                <Button
                  size="small"
                  icon={<Zap size={14} />}
                  loading={testingForm}
                  onClick={() => void handleTestFormModel()}
                >
                  {t("models.testConnection")}
                </Button>
              )}
              <Button size="small" onClick={resetForm}>
                {t("common.cancel")}
              </Button>
              <Button
                type="primary"
                size="small"
                onClick={() =>
                  void (isEditing ? handleEditModel() : handleAddModel())
                }
              >
                {isEditing ? t("models.saveEdit") : t("models.addModel")}
              </Button>
            </div>
          </Form>
        </div>
      ) : (
        <Button
          type="dashed"
          block
          icon={<Plus size={14} />}
          onClick={startAdding}
          style={{ marginTop: 12 }}
        >
          {t("models.addModel")}
        </Button>
      )}
    </div>
  );
}
