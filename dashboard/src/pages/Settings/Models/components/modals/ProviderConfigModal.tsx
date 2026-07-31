/**
 * ProviderConfigModal — edit existing provider + manage models + Ollama support.
 *
 * Extends the original octop ProviderConfigModal with:
 *   - Embedded ModelListEditor for per-model enable/disable/add/delete
 *   - Ollama section (only shown when kind=openai and name/base_url suggests Ollama)
 *     with local model list, download, and delete UI
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Divider, Form, Input, Modal, Select } from "antd";
import { message } from "@/utils/antdMessage";

import { Download, Key, Loader2, Trash2, X, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../../../api/request";
import type { ProviderRow, ProviderModel } from "../../useProviders";
import { fetchProviderModels, testProviderDraft } from "../../providerApi";
import { getProviderDocs } from "../../../../../assets/providers";
import { ModelListEditor } from "./ModelListEditor";
import styles from "../../index.module.less";

const POLL_INTERVAL_MS = 3000;

interface OllamaModelResponse {
  name: string;
  size: number;
  digest?: string | null;
  modified_at?: string | null;
}

interface OllamaDownloadTaskResponse {
  task_id: string;
  status: string;
  name: string;
  error?: string | null;
  result?: OllamaModelResponse | null;
}

interface ProviderConfigForm {
  base_url?: string;
  api_key?: string;
  model?: string;
  note?: string;
  kind: string;
}

interface ProviderConfigModalProps {
  provider: ProviderRow;
  open: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
  /** API path prefix for PATCH/test. Defaults to "/providers". */
  apiPrefix?: string;
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function isOllamaProvider(provider: ProviderRow): boolean {
  return (
    provider.name === "ollama" ||
    provider.name === "Ollama (Local)" ||
    (provider.base_url?.includes("11434") ?? false) ||
    (provider.base_url?.includes("ollama") ?? false)
  );
}

export function ProviderConfigModal({
  provider,
  open,
  onClose,
  onSaved,
  apiPrefix = "/providers",
}: ProviderConfigModalProps) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  const [formDirty, setFormDirty] = useState(false);
  const [testing, setTesting] = useState(false);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [form] = Form.useForm<ProviderConfigForm>();
  const [draftModels, setDraftModels] = useState<ProviderModel[]>([]);

  const hasApiKey = !!provider.api_key && provider.api_key.length > 0;
  const isOllama = isOllamaProvider(provider);

  // === Ollama states ===
  const [downloadForm] = Form.useForm();
  const [ollamaModels, setOllamaModels] = useState<OllamaModelResponse[]>([]);
  const [loadingOllama, setLoadingOllama] = useState(false);
  const [ollamaUnavailable, setOllamaUnavailable] = useState(false);
  const [ollamaTasks, setOllamaTasks] = useState<OllamaDownloadTaskResponse[]>(
    [],
  );
  const ollamaPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const ollamaNotifiedRef = useRef<Set<string>>(new Set());

  const stopOllamaPolling = useCallback(() => {
    if (ollamaPollRef.current) {
      clearInterval(ollamaPollRef.current);
      ollamaPollRef.current = null;
    }
  }, []);

  const fetchOllamaModels = useCallback(async () => {
    setLoadingOllama(true);
    setOllamaUnavailable(false);
    try {
      const data = await request<OllamaModelResponse[]>("/ollama-models");
      setOllamaModels(Array.isArray(data) ? data : []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("503") || msg.includes("connect")) {
        setOllamaUnavailable(true);
      }
      setOllamaModels([]);
    } finally {
      setLoadingOllama(false);
    }
  }, []);

  const pollOllamaDownloads = useCallback(async () => {
    try {
      const tasks = await request<OllamaDownloadTaskResponse[]>(
        "/ollama-models/download-status",
      );
      const taskList = Array.isArray(tasks) ? tasks : [];
      const active = taskList.filter(
        (tk) => tk.status === "pending" || tk.status === "downloading",
      );
      const terminal = taskList.filter(
        (tk) =>
          tk.status === "completed" ||
          tk.status === "failed" ||
          tk.status === "cancelled",
      );

      let needsRefresh = false;
      for (const task of terminal) {
        if (!ollamaNotifiedRef.current.has(task.task_id)) {
          ollamaNotifiedRef.current.add(task.task_id);
          if (task.status === "completed") {
            message.success(t("models.localDownloadSuccess"));
            needsRefresh = true;
          } else if (task.status === "cancelled") {
            message.info(t("models.localDownloadCancelled"));
          } else {
            message.error(task.error || t("models.localDownloadFailed"));
          }
        }
      }

      if (needsRefresh) {
        await onSaved();
        await fetchOllamaModels();
      }

      setOllamaTasks(active);
      if (active.length === 0) stopOllamaPolling();
    } catch {
      /* ignore polling errors */
    }
  }, [t, onSaved, fetchOllamaModels, stopOllamaPolling]);

  const startOllamaPolling = useCallback(() => {
    if (ollamaPollRef.current) return;
    ollamaPollRef.current = setInterval(
      () => void pollOllamaDownloads(),
      POLL_INTERVAL_MS,
    );
  }, [pollOllamaDownloads]);

  useEffect(() => {
    if (!open || !isOllama) return;

    void fetchOllamaModels();
    downloadForm.resetFields();
    ollamaNotifiedRef.current.clear();

    void request<OllamaDownloadTaskResponse[]>("/ollama-models/download-status")
      .then((tasks) => {
        const active = (Array.isArray(tasks) ? tasks : []).filter(
          (tk) => tk.status === "pending" || tk.status === "downloading",
        );
        setOllamaTasks(active);
        if (active.length > 0) startOllamaPolling();
      })
      .catch(() => {});

    return () => stopOllamaPolling();
  }, [
    open,
    isOllama,
    fetchOllamaModels,
    downloadForm,
    startOllamaPolling,
    stopOllamaPolling,
  ]);

  const handleOllamaDownload = async () => {
    try {
      const values = await downloadForm.validateFields();
      const task = await request<OllamaDownloadTaskResponse>(
        "/ollama-models/download",
        {
          method: "POST",
          body: JSON.stringify({
            name: (values as { name: string }).name.trim(),
          }),
        },
      );
      setOllamaTasks((prev) => [...prev, task]);
      downloadForm.resetFields();
      startOllamaPolling();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error ? err.message : t("models.localDownloadFailed"),
      );
    }
  };

  const handleOllamaDelete = (model: OllamaModelResponse) => {
    Modal.confirm({
      title: t("models.localDeleteModel"),
      content: t("models.localDeleteConfirm", { name: model.name }),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await request(`/ollama-models/${encodeURIComponent(model.name)}`, {
            method: "DELETE",
          });
          message.success(t("models.localModelDeleted", { name: model.name }));
          await onSaved();
          await fetchOllamaModels();
        } catch (err) {
          message.error(
            err instanceof Error ? err.message : t("models.localDeleteFailed"),
          );
        }
      },
    });
  };

  const handleCancelOllamaDownload = (task: OllamaDownloadTaskResponse) => {
    Modal.confirm({
      title: t("models.localCancelDownload"),
      content: t("models.localCancelDownloadConfirm", { repo: task.name }),
      okText: t("models.localCancelDownload"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await request(`/ollama-models/download/${task.task_id}`, {
            method: "DELETE",
          });
          message.success(t("models.localDownloadCancelled"));
          setOllamaTasks((prev) =>
            prev.filter((tk) => tk.task_id !== task.task_id),
          );
        } catch (err) {
          message.error(
            err instanceof Error
              ? err.message
              : t("models.localCancelDownloadFailed"),
          );
        }
      },
    });
  };

  // ======================== Form ========================

  const apiKeyExtra = useMemo(() => {
    const hint = hasApiKey
      ? t("models.apiKeyExtraConfigured")
      : t("models.apiKeyExtraOptional");
    const nameSlug = provider.name.toLowerCase().replace(/\s+/g, "-");
    const docsUrl =
      getProviderDocs(provider.name) ??
      getProviderDocs(provider.name.toLowerCase()) ??
      getProviderDocs(nameSlug);
    if (!docsUrl) return hint;
    return (
      <>
        {hint}{" "}
        <a
          href={docsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.getApiKeyLink}
        >
          <Key size={12} style={{ marginRight: 4 }} />
          {t("models.getApiKey")}
        </a>
      </>
    );
  }, [hasApiKey, provider.name, t]);

  const apiKeyPlaceholder = useMemo(() => {
    if (hasApiKey) return t("models.apiKeyPlaceholderKeep");
    return "sk-...";
  }, [hasApiKey, t]);

  useEffect(() => {
    if (!open) return;
    // Only hydrate when the modal opens (or provider id changes), so
    // background refreshes / local model toggles do not reset the form.
    const currentDefaultModel = provider.models?.length
      ? provider.models[0].id
      : "";
    form.setFieldsValue({
      kind: provider.kind,
      base_url: provider.base_url ?? "",
      api_key: undefined,
      model: currentDefaultModel,
      note: provider.note ?? "",
    });
    setDraftModels(
      (provider.models ?? []).map((m) => ({
        ...m,
        enabled: m.enabled !== false,
      })),
    );
    setFormDirty(false);
  }, [open, provider.id, form]);

  const handleModelsChange = (models: ProviderModel[]) => {
    setDraftModels(models);
    setFormDirty(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);

      const payload: Record<string, unknown> = {};
      if (values.kind !== provider.kind) payload.kind = values.kind;
      if ((values.base_url ?? "") !== (provider.base_url ?? ""))
        payload.base_url = values.base_url?.trim() || null;
      if (values.api_key !== undefined && values.api_key !== "")
        payload.api_key = values.api_key.trim();
      if ((values.note ?? "") !== (provider.note ?? ""))
        payload.note = values.note?.trim() || null;
      // default model
      const existingDefault = provider.models?.length
        ? provider.models[0].id
        : "";
      if ((values.model ?? "") !== existingDefault)
        payload.model = values.model?.trim() || null;

      const modelsChanged =
        JSON.stringify(
          (provider.models ?? []).map((m) => ({
            ...m,
            enabled: m.enabled !== false,
          })),
        ) !== JSON.stringify(draftModels);
      if (modelsChanged) {
        payload.models = draftModels;
      }

      if (Object.keys(payload).length === 0) {
        message.info(t("models.noChanges"));
        setSaving(false);
        return;
      }

      await request(`${apiPrefix}/${provider.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      message.success(t("models.providerConfigSaved", { name: provider.name }));
      await onSaved();
      setFormDirty(false);
      onClose();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error ? err.message : t("common.saveFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleRevoke = () => {
    Modal.confirm({
      title: t("models.revokeConfirmTitle"),
      content: t("models.revokeConfirmContentSimple", { name: provider.name }),
      okText: t("models.revoke"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await request(`${apiPrefix}/${provider.id}`, {
            method: "PATCH",
            body: JSON.stringify({ api_key: null }),
          });
          await onSaved();
          onClose();
          message.success(
            t("models.authorizationRevokedSimpleAlt", { name: provider.name }),
          );
        } catch (err) {
          message.error(
            err instanceof Error ? err.message : t("models.revokeFailedSimple"),
          );
        }
      },
    });
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const values = form.getFieldsValue();
      const modelId =
        (values.model as string | undefined)?.trim() ||
        draftModels.find((m) => m.enabled !== false)?.id ||
        draftModels[0]?.id;
      if (!modelId) {
        message.warning(t("models.testDraftNeedModel"));
        return;
      }
      const draftApiKey = (values.api_key as string | undefined)?.trim();
      const draftBaseUrl = (values.base_url as string | undefined)?.trim();
      const useDraft =
        !!draftApiKey ||
        (!!draftBaseUrl && draftBaseUrl !== (provider.base_url ?? ""));

      if (useDraft && !draftApiKey && !hasApiKey) {
        message.warning(t("models.pleaseEnterApiKey"));
        return;
      }

      const result =
        useDraft || !hasApiKey
          ? await testProviderDraft({
              name: provider.name,
              kind: provider.kind,
              api_key: draftApiKey || provider.api_key || undefined,
              base_url: draftBaseUrl || provider.base_url,
              model_id: modelId,
            })
          : await request<{
              ok: boolean;
              latency_ms?: number;
              error?: string;
            }>(`${apiPrefix}/${provider.id}/test`, {
              method: "POST",
              body: JSON.stringify({ model_id: modelId }),
            });

      if (result.ok) {
        const latency =
          result.latency_ms != null
            ? t("models.testConnectionLatency", { time: result.latency_ms })
            : "";
        message.success(
          t("models.testConnectionSuccess", {
            name: provider.name,
            latency,
          }),
        );
      } else {
        message.error(
          t("models.testConnectionFailed", {
            error: result.error ?? "unknown",
          }),
        );
      }
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("models.testFailedSimple"),
      );
    } finally {
      setTesting(false);
    }
  };

  const handleFetchModels = async () => {
    try {
      const values = form.getFieldsValue();
      const kind = (values.kind as string | undefined) ?? provider.kind;
      if (kind !== "openai") {
        message.warning(t("models.fetchModelsUnsupportedKind"));
        return;
      }
      const draftApiKey = (values.api_key as string | undefined)?.trim();
      const draftBaseUrl = (values.base_url as string | undefined)?.trim();
      const apiKey = draftApiKey || provider.api_key || "";
      if (!apiKey) {
        message.warning(t("models.pleaseEnterApiKey"));
        return;
      }

      setFetchingModels(true);
      const result = await fetchProviderModels({
        kind: "openai",
        api_key: apiKey,
        base_url: draftBaseUrl || provider.base_url,
      });
      if (!result.ok) {
        message.error(
          t("models.fetchModelsFailed", {
            error: result.error ?? "unknown",
          }),
        );
        return;
      }
      const fetched = result.models ?? [];
      if (fetched.length === 0) {
        message.info(t("models.fetchModelsNoNew"));
        return;
      }

      const existingIds = new Set(draftModels.map((m) => m.id));
      const missing = fetched.filter((m) => !existingIds.has(m.id));
      if (missing.length === 0) {
        message.info(t("models.fetchModelsNoNew"));
        return;
      }

      const added: ProviderModel[] = missing.map((m) => ({
        id: m.id,
        name: m.name || m.id,
        enabled: false,
        input: ["text"],
        thinking: null,
      }));
      setDraftModels((prev) => [...prev, ...added]);
      setFormDirty(true);
      message.success(t("models.fetchModelsMerged", { count: missing.length }));
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("models.fetchModelsFailed", { error: "unknown" }),
      );
    } finally {
      setFetchingModels(false);
    }
  };

  return (
    <Modal
      title={t("models.configureProviderTitle", { name: provider.name })}
      open={open}
      onCancel={onClose}
      width={600}
      destroyOnHidden
      footer={
        <div className={styles.modalFooter}>
          <div className={styles.modalFooterLeft}>
            {hasApiKey && (
              <Button danger size="small" onClick={handleRevoke}>
                {t("models.revokeAuthorization")}
              </Button>
            )}
          </div>
          <div className={styles.modalFooterRight}>
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            <Button
              type="primary"
              loading={saving}
              disabled={!formDirty}
              onClick={handleSubmit}
            >
              {t("common.save")}
            </Button>
          </div>
        </div>
      }
    >
      {/* ===== Provider connection form ===== */}
      <Form
        form={form}
        layout="vertical"
        onValuesChange={() => setFormDirty(true)}
      >
        <Form.Item
          name="kind"
          label={t("models.kindLabel")}
          rules={[{ required: true }]}
        >
          <Input disabled style={{ color: "var(--fn-text-secondary)" }} />
        </Form.Item>

        <Form.Item
          name="base_url"
          label="Base URL"
          extra={t("models.baseUrlExtra")}
        >
          <Input placeholder="https://api.openai.com/v1" />
        </Form.Item>

        <Form.Item name="api_key" label="API Key" extra={apiKeyExtra}>
          <Input.Password placeholder={apiKeyPlaceholder} visibilityToggle />
        </Form.Item>

        {/* Default model — Select from the models list, or type freely */}
        <Form.Item
          name="model"
          label={t("models.defaultModelLabel")}
          extra={t(
            "models.defaultModelExtra",
            "测试连接时使用此模型；留空则使用第一个已启用的模型",
          )}
        >
          {draftModels.length ? (
            <Select
              showSearch
              allowClear
              placeholder={t("models.defaultModelPlaceholder")}
              options={draftModels.map((m) => ({
                value: m.id,
                label: m.name !== m.id ? `${m.name} (${m.id})` : m.id,
              }))}
            />
          ) : (
            <Input placeholder={t("models.defaultModelPlaceholder")} />
          )}
        </Form.Item>

        <Form.Item name="note" label={t("models.noteLabel")}>
          <Input.TextArea rows={2} placeholder={t("models.notePlaceholder")} />
        </Form.Item>
      </Form>

      <div style={{ marginBottom: 16 }}>
        <Button
          size="small"
          icon={<Zap size={12} />}
          loading={testing}
          onClick={handleTest}
        >
          {t("models.testConnection")}
        </Button>
        <Button
          size="small"
          icon={<Download size={12} />}
          loading={fetchingModels}
          onClick={handleFetchModels}
          style={{ marginLeft: 8 }}
        >
          {t("models.fetchModels")}
        </Button>
      </div>

      {/* ===== Models section ===== */}
      <Divider orientation="left" style={{ fontSize: 13 }}>
        {t("models.manageModels")}
      </Divider>

      <ModelListEditor
        provider={provider}
        models={draftModels}
        onModelsChange={handleModelsChange}
        apiPrefix={apiPrefix}
      />

      {/* ===== Ollama local models section ===== */}
      {isOllama && (
        <>
          <Divider orientation="left" style={{ fontSize: 13, marginTop: 24 }}>
            {t("models.ollamaLocalModels")}
          </Divider>

          {ollamaUnavailable ? (
            <div
              style={{
                fontSize: 12,
                color: "var(--fn-text-tertiary)",
                padding: "8px 0",
              }}
            >
              {t("models.ollamaUnavailable")}
            </div>
          ) : loadingOllama ? (
            <div style={{ padding: "8px 0", fontSize: 12 }}>
              <Loader2 size={12} style={{ marginRight: 6 }} />
              {t("models.loading")}
            </div>
          ) : (
            <>
              {/* Local models list */}
              {ollamaModels.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  {ollamaModels.map((m) => (
                    <div
                      key={m.name}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "6px 0",
                        borderBottom:
                          "1px solid var(--ant-color-split, rgba(0,0,0,0.06))",
                      }}
                    >
                      <div>
                        <span style={{ fontSize: 13, fontWeight: 500 }}>
                          {m.name}
                        </span>
                        {m.size > 0 && (
                          <span
                            style={{
                              fontSize: 11,
                              color: "var(--fn-text-tertiary)",
                              marginLeft: 8,
                            }}
                          >
                            {formatFileSize(m.size)}
                          </span>
                        )}
                      </div>
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<Trash2 size={14} />}
                        onClick={() => handleOllamaDelete(m)}
                      />
                    </div>
                  ))}
                </div>
              )}

              {/* Active download tasks */}
              {ollamaTasks.map((task) => (
                <div
                  key={task.task_id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "6px 0",
                    borderBottom:
                      "1px solid var(--ant-color-split, rgba(0,0,0,0.06))",
                  }}
                >
                  <Loader2 size={12} />
                  <span style={{ fontSize: 13, flex: 1 }}>
                    {t("models.localDownloading", { repo: task.name })}
                  </span>
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<X size={14} />}
                    onClick={() => handleCancelOllamaDownload(task)}
                  />
                </div>
              ))}
            </>
          )}

          {/* Download form */}
          <Form
            form={downloadForm}
            layout="inline"
            style={{ marginTop: 12, gap: 8 }}
          >
            <Form.Item
              name="name"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <Input
                placeholder={t("models.ollamaModelNamePlaceholder")}
                style={{ width: "100%" }}
              />
            </Form.Item>
            <Form.Item>
              <Button
                type="primary"
                icon={<Download size={14} />}
                onClick={handleOllamaDownload}
              >
                {t("models.localDownloadModel")}
              </Button>
            </Form.Item>
          </Form>
        </>
      )}
    </Modal>
  );
}
