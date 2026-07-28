/**
 * CustomProviderModal — create a new custom provider.
 */
import { useEffect, useMemo, useState } from "react";
import { Button, Divider, Form, Input, Modal, Select, Space, message } from "antd";
import { Download, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../../../api/request";
import type { ProviderModel, ProviderRow } from "../../useProviders";
import { fetchProviderModels, testProviderDraft } from "../../providerApi";
import { ModelListEditor } from "./ModelListEditor";
import styles from "../../index.module.less";

interface CustomProviderModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
  /** API path prefix for POST. Defaults to "/providers". */
  apiPrefix?: string;
}

const KINDS = [
  { value: "openai", labelKey: "kindOpenaiCompat" as const },
  { value: "anthropic", labelKey: "anthropic" as const },
  { value: "bedrock", labelKey: "bedrock" as const },
];

export function CustomProviderModal({
  open,
  onClose,
  onSaved,
  apiPrefix = "/providers",
}: CustomProviderModalProps) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [form] = Form.useForm<{
    name: string;
    kind: string;
    base_url?: string;
    api_key?: string;
    note?: string;
  }>();
  const kind = Form.useWatch("kind", form) as string | undefined;
  const apiKey = Form.useWatch("api_key", form) as string | undefined;
  const [models, setModels] = useState<ProviderModel[]>([]);
  const canTest = !!apiKey?.trim();

  const draftProvider = useMemo<ProviderRow>(
    () => ({
      id: 0,
      name: (form.getFieldValue("name") as string | undefined) || "draft",
      kind: (form.getFieldValue("kind") as string | undefined) || "openai",
      base_url: (form.getFieldValue("base_url") as string | undefined) || null,
      api_key: (form.getFieldValue("api_key") as string | undefined) || null,
      models,
      note: null,
      enabled: true,
    }),
    [form, models],
  );

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({ kind: "openai" });
      setModels([]);
    }
  }, [open, form]);

  const testDraftModel = async (modelId: string) => {
    const values = await form.validateFields(["name", "kind", "api_key", "base_url"]);
    const key = (values.api_key as string | undefined)?.trim();
    if (!key) {
      return { ok: false, error: t("models.pleaseEnterApiKey") };
    }
    return testProviderDraft({
      name: (values.name || "draft").trim(),
      kind: values.kind,
      api_key: key,
      base_url: values.base_url?.trim() || null,
      model_id: modelId,
    });
  };

  const handleFetchModels = async () => {
    try {
      const values = await form.validateFields(["kind", "api_key", "base_url"]);
      if ((values.kind as string) !== "openai") {
        message.warning(t("models.fetchModelsUnsupportedKind"));
        return;
      }
      const apiKey = (values.api_key as string | undefined)?.trim();
      if (!apiKey) {
        message.warning(t("models.pleaseEnterApiKey"));
        return;
      }
      setFetchingModels(true);
      const result = await fetchProviderModels({
        kind: "openai",
        api_key: apiKey,
        base_url: (values.base_url as string | undefined)?.trim() || null,
      });
      if (!result.ok) {
        message.error(
          t("models.fetchModelsFailed", {
            error: result.error ?? "unknown",
          }),
        );
        return;
      }
      const remote: ProviderModel[] = (result.models ?? []).map((m) => ({
        id: m.id,
        name: m.name || m.id,
        enabled: false,
        input: ["text"],
        thinking: null,
      }));
      let addedCount = 0;
      setModels((prev) => {
        const existing = new Set(prev.map((m) => m.id));
        const added = remote.filter((m) => !existing.has(m.id));
        addedCount = added.length;
        return [...prev, ...added];
      });
      if (addedCount === 0) {
        message.info(t("models.fetchModelsNoNew"));
      } else {
        message.success(t("models.fetchModelsMerged", { count: addedCount }));
      }
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error
          ? err.message
          : t("models.fetchModelsFailed", { error: "unknown" }),
      );
    } finally {
      setFetchingModels(false);
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);

      const modelEntries = models.map((m) => {
        const entry: Record<string, unknown> = {
          id: m.id,
          name: m.name,
          enabled: m.enabled,
          input: m.input.length > 0 ? m.input : ["text"],
          thinking: null,
        };
        if (m.max_tokens != null) entry.max_tokens = m.max_tokens;
        if (m.context_window != null) entry.context_window = m.context_window;
        if (m.reasoning) entry.reasoning = true;
        return entry;
      });

      await request<ProviderRow>(apiPrefix, {
        method: "POST",
        body: JSON.stringify({
          name: (values.name as string).trim(),
          kind: values.kind as string,
          base_url: (values.base_url as string | undefined)?.trim() || null,
          api_key: (values.api_key as string | undefined)?.trim() || null,
          models: modelEntries.length > 0 ? modelEntries : [],
          note: (values.note as string | undefined)?.trim() || null,
        }),
      });
      message.success(
        t("models.providerCreatedSimple", {
          name: (values.name as string).trim(),
        }),
      );
      await onSaved();
      onClose();
    } catch (error) {
      if (error && typeof error === "object" && "errorFields" in error) return;
      const errMsg =
        error instanceof Error ? error.message : t("models.createFailedSimple");
      message.error(errMsg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={t("models.addCustomProvider")}
      open={open}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={saving}
      okText={t("common.create")}
      cancelText={t("common.cancel")}
      destroyOnHidden
      width={560}
      footer={
        <div className={styles.modalFooter}>
          <div className={styles.modalFooterLeft} />
          <div className={styles.modalFooterRight}>
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            <Button type="primary" loading={saving} onClick={() => void handleSubmit()}>
              {t("common.create")}
            </Button>
          </div>
        </div>
      }
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item
          name="name"
          label={t("models.nameLabel")}
          rules={[{ required: true, message: t("models.pleaseEnterName") }]}
        >
          <Input placeholder={t("models.namePlaceholder")} />
        </Form.Item>

        <Form.Item
          name="kind"
          label={t("models.kindLabel")}
          rules={[{ required: true, message: t("models.pleaseSelectKind") }]}
        >
          <Select
            options={KINDS.map((k) => ({
              value: k.value,
              label:
                k.value === "openai"
                  ? t("models.kindOpenaiCompat")
                  : k.value === "anthropic"
                    ? "Anthropic"
                    : "AWS Bedrock",
            }))}
          />
        </Form.Item>

        <Form.Item
          name="base_url"
          label="Base URL"
          extra={t("models.baseUrlExtra")}
        >
          <Input placeholder="https://api.openai.com/v1" />
        </Form.Item>

        <Form.Item name="api_key" label="API Key">
          <Input.Password placeholder="sk-..." visibilityToggle />
        </Form.Item>

        {kind === "openai" && (
          <Form.Item style={{ marginBottom: 12 }}>
            <Button
              icon={<Download size={14} />}
              loading={fetchingModels}
              onClick={() => void handleFetchModels()}
            >
              {fetchingModels
                ? t("models.fetchingModels")
                : t("models.fetchModels")}
            </Button>
          </Form.Item>
        )}

        <Form.Item name="note" label={t("models.noteLabel")}>
          <Input.TextArea rows={2} placeholder={t("models.notePlaceholder")} />
        </Form.Item>
      </Form>

      <div style={{ marginBottom: 16 }}>
        <Button size="small" icon={<Zap size={12} />} loading={testing} onClick={async () => {
          try {
            setTesting(true);
            const modelId = models.find((m) => m.enabled !== false)?.id || models[0]?.id;
            if (!modelId) {
              message.warning(t("models.testDraftNeedModel"));
              return;
            }
            const result = await testDraftModel(modelId);
            if (result.ok) {
              const latency = result.latency_ms != null ? t("models.testConnectionLatency", { time: result.latency_ms }) : "";
              message.success(t("models.testConnectionSuccess", { name: (form.getFieldValue("name") as string) || "draft", latency }));
            } else {
              message.error(t("models.testConnectionFailed", { error: result.error ?? "unknown" }));
            }
          } finally {
            setTesting(false);
          }
        }}>
          {t("models.testConnection")}
        </Button>
        {kind === "openai" && (
          <Button size="small" icon={<Download size={12} />} loading={fetchingModels} onClick={() => void handleFetchModels()} style={{ marginLeft: 8 }}>
            {t("models.fetchModels")}
          </Button>
        )}
      </div>

      <Divider orientation="left" style={{ fontSize: 13 }}>
        {t("models.manageModels")}
      </Divider>
      <ModelListEditor
        provider={draftProvider}
        models={models}
        onModelsChange={setModels}
        apiPrefix={apiPrefix}
        canTest={canTest}
        onTestModel={(modelId) => testDraftModel(modelId)}
      />
    </Modal>
  );
}
