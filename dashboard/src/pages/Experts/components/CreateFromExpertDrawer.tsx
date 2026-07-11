// dashboard/src/pages/Experts/components/CreateFromExpertDrawer.tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Collapse,
  Drawer,
  Form,
  Input,
  Select,
  Spin,
  message,
} from "antd";
import { request } from "../../../api/request";
import { apiErrorMessage } from "../../../utils/apiError";
import { useAgentFormResources } from "../../../hooks/useAgentFormResources";
import { pickLocale } from "../../../utils/localizedText";
import {
  buildModelSelectOptions,
  defaultModelFromForm,
  MODEL_AUTO_VALUE,
} from "../../../utils/modelOptions";
import type { ExpertSummary } from "./ExpertCard";
import { groupExpertFiles, type NamedFileContent } from "./expertFileGroups";
import { metaForFile } from "./iconForName";
import { useSkillSlugDisplayName } from "../../Agent/Skills/skillDisplayNames";
import {
  buildBackendSpec,
  DEFAULT_BACKEND,
  probeRootDir,
  rootDirProbeMessage,
  shouldProbeRootDir,
  validatePathMappings,
  type PathMapping,
} from "./agentBackendForm";
import AgentBackendFields from "./AgentBackendFields";
import styles from "../index.module.less";

type FileContent = NamedFileContent;

interface ExpertDetail {
  file_contents?: FileContent[];
}

interface CreateFromExpertDrawerProps {
  open: boolean;
  expert: ExpertSummary | null;
  lang: "zh" | "en";
  onClose: () => void;
  onCreated: (agentId: string, agentName: string) => void;
}

export default function CreateFromExpertDrawer({
  open,
  expert,
  lang,
  onClose,
  onCreated,
}: CreateFromExpertDrawerProps) {
  const { t } = useTranslation();
  const skillSlugDisplayName = useSkillSlugDisplayName();
  const [form] = Form.useForm<{
    name: string;
    description: string;
    default_model: string;
    backend_choice: string;
    composite_default: string;
    root_dir?: string;
  }>();
  const [submitting, setSubmitting] = useState(false);

  const { models, modelsLoading, backends, backendsLoading } =
    useAgentFormResources(open && !!expert);

  const [pathMappings, setPathMappings] = useState<PathMapping[]>([]);

  const [fileContents, setFileContents] = useState<FileContent[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  const backendChoice =
    Form.useWatch("backend_choice", form) ?? DEFAULT_BACKEND;

  useEffect(() => {
    if (!open || !expert) return;
    let cancelled = false;

    setPathMappings([]);
    form.setFieldsValue({
      name: pickLocale(expert.label, lang) || expert.id,
      description: pickLocale(expert.description, lang),
      default_model: MODEL_AUTO_VALUE,
      backend_choice: DEFAULT_BACKEND,
      composite_default: DEFAULT_BACKEND,
    });

    setDetailLoading(true);
    request<ExpertDetail>(`/experts/${encodeURIComponent(expert.id)}`)
      .then((data) => {
        if (!cancelled) setFileContents(data.file_contents ?? []);
      })
      .catch(() => {
        if (!cancelled) setFileContents([]);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, expert, lang, form]);

  const handleCreate = async () => {
    if (!expert) return;
    const values = await form.validateFields();
    if (values.backend_choice === "composite") {
      const pathError = validatePathMappings(pathMappings, t);
      if (pathError) {
        message.error(pathError);
        return;
      }
    }
    if (shouldProbeRootDir(values.backend_choice, values.root_dir)) {
      const probe = await probeRootDir(values.root_dir ?? "/");
      if (!probe.ok) {
        message.error(
          `${rootDirProbeMessage(probe, t)}\n${t("experts.rootDirProbe.guidance")}`,
        );
        return;
      }
    }
    setSubmitting(true);
    try {
      const backendSpec = buildBackendSpec(
        values.backend_choice,
        values.composite_default ?? DEFAULT_BACKEND,
        pathMappings,
        values.root_dir,
      );

      const body = await request<{ agent_id: string; name: string }>(
        `/agents/from-expert/${encodeURIComponent(expert.id)}`,
        {
          method: "POST",
          body: JSON.stringify({
            name: values.name,
            description: values.description || undefined,
            default_model:
              defaultModelFromForm(values.default_model) ?? undefined,
            backend: backendSpec,
          }),
        },
      );
      message.success(t("experts.agentCreated", { name: body.name }));
      form.resetFields();
      onCreated(body.agent_id, body.name);
    } catch (err) {
      message.error(apiErrorMessage(err, t("experts.createFailed"), t));
    } finally {
      setSubmitting(false);
    }
  };

  const addPathMapping = () =>
    setPathMappings((prev) => [...prev, { path: "", backend: "" }]);
  const removePathMapping = (index: number) =>
    setPathMappings((prev) => prev.filter((_, i) => i !== index));
  const updatePathMapping = (
    index: number,
    field: keyof PathMapping,
    value: string,
  ) =>
    setPathMappings((prev) =>
      prev.map((m, i) => (i === index ? { ...m, [field]: value } : m)),
    );

  const hasNoModels = !modelsLoading && models.length === 0;
  const modelOptions = buildModelSelectOptions(
    models,
    t("experts.defaultModelAuto"),
  );
  const createBlocked = submitting || hasNoModels;

  const { configFiles, skillGroups } = groupExpertFiles(fileContents);

  const title = expert
    ? t("experts.createDrawerTitle", {
        name: pickLocale(expert.label, lang) || expert.id,
      })
    : "";

  return (
    <Drawer
      open={open}
      title={title}
      width={520}
      onClose={onClose}
      destroyOnClose
      footer={
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className={styles.drawerCancelBtn} onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button
            className={styles.drawerSaveBtn}
            onClick={() => void handleCreate()}
            disabled={createBlocked}
            title={hasNoModels ? t("experts.noModelsWarning") : undefined}
          >
            {submitting ? t("experts.creating") : t("common.create")}
          </button>
        </div>
      }
    >
      {hasNoModels && (
        <Alert
          type="warning"
          showIcon
          message={t("experts.noModelsWarning")}
          action={
            <a href="/admin/providers" style={{ whiteSpace: "nowrap" }}>
              {t("experts.goToAdmin")}
            </a>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      <Form form={form} layout="vertical" size="middle">
        <Form.Item
          name="name"
          label={t("experts.agentName")}
          rules={[{ required: true, message: t("experts.pleaseEnterName") }]}
        >
          <Input />
        </Form.Item>

        <Form.Item name="description" label={t("experts.agentDescription")}>
          <Input.TextArea rows={2} />
        </Form.Item>

        <Form.Item
          name="default_model"
          label={t("experts.defaultModelLabel")}
          initialValue={MODEL_AUTO_VALUE}
        >
          <Select
            loading={modelsLoading}
            options={modelOptions}
            placeholder={t("experts.defaultModelPlaceholder")}
            showSearch
            filterOption={(input, opt) =>
              ((opt?.label as string) ?? "")
                .toLowerCase()
                .includes(input.toLowerCase())
            }
          />
        </Form.Item>

        <AgentBackendFields
          backends={backends}
          backendsLoading={backendsLoading}
          backendChoice={backendChoice}
          pathMappings={pathMappings}
          onAddPathMapping={addPathMapping}
          onRemovePathMapping={removePathMapping}
          onUpdatePathMapping={updatePathMapping}
        />
      </Form>

      {detailLoading ? (
        <div style={{ textAlign: "center", padding: "16px 0" }}>
          <Spin size="small" />
        </div>
      ) : (
        <>
          {configFiles.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>
                {t("experts.mdFilesTitle")}
              </div>
              <p
                style={{
                  fontSize: 12,
                  color: "var(--fn-text-tertiary)",
                  margin: "0 0 8px",
                }}
              >
                {t("experts.mdFilesHint")}
              </p>
              <Collapse
                size="small"
                items={configFiles.map((f) => {
                  const meta = metaForFile(f.name, t);
                  return {
                    key: f.name,
                    label: (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "baseline",
                          gap: 8,
                        }}
                      >
                        <span style={{ fontWeight: 500 }}>{meta.label}</span>
                        <span
                          style={{
                            fontSize: 11,
                            color:
                              "var(--fn-text-quaternary, var(--fn-text-tertiary))",
                          }}
                        >
                          {f.name}
                        </span>
                      </span>
                    ),
                    children: (
                      <pre
                        style={{
                          fontSize: 12,
                          maxHeight: 200,
                          overflowY: "auto",
                          background: "var(--fn-bg-secondary, #f5f5f5)",
                          padding: 8,
                          borderRadius: 4,
                          margin: 0,
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        }}
                      >
                        {f.content}
                      </pre>
                    ),
                  };
                })}
              />
            </div>
          )}

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>
              {t("experts.skillFilesTitle", { count: skillGroups.length })}
            </div>
            <p
              style={{
                fontSize: 12,
                color: "var(--fn-text-tertiary)",
                margin: "0 0 8px",
              }}
            >
              {t("experts.skillFilesHint")}
            </p>
            {skillGroups.length === 0 ? (
              <div
                style={{
                  fontSize: 13,
                  color: "var(--fn-text-tertiary)",
                  padding: "4px 0",
                }}
              >
                {t("experts.noSkillFiles")}
              </div>
            ) : (
              <Collapse
                size="small"
                items={skillGroups.map((group) => ({
                  key: group.name,
                  label: skillSlugDisplayName(group.name),
                  children: (
                    <Collapse
                      size="small"
                      items={group.files.map((f) => {
                        const skillBasename = f.name.replace(
                          `skills/${group.name}/`,
                          "",
                        );
                        const skillMeta = metaForFile(skillBasename, t);
                        return {
                          key: f.name,
                          label: (
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "baseline",
                                gap: 8,
                              }}
                            >
                              <span style={{ fontWeight: 500 }}>
                                {skillMeta.label}
                              </span>
                              <span
                                style={{
                                  fontSize: 11,
                                  color:
                                    "var(--fn-text-quaternary, var(--fn-text-tertiary))",
                                }}
                              >
                                {skillBasename}
                              </span>
                            </span>
                          ),
                          children: (
                            <pre
                              style={{
                                fontSize: 12,
                                maxHeight: 200,
                                overflowY: "auto",
                                background: "var(--fn-bg-secondary, #f5f5f5)",
                                padding: 8,
                                borderRadius: 4,
                                margin: 0,
                                whiteSpace: "pre-wrap",
                                wordBreak: "break-word",
                              }}
                            >
                              {f.content}
                            </pre>
                          ),
                        };
                      })}
                    />
                  ),
                }))}
              />
            )}
          </div>
        </>
      )}
    </Drawer>
  );
}
