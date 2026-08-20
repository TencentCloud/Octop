// dashboard/src/pages/Experts/components/CreateFromExpertDrawer.tsx
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, Collapse, Drawer, Form, Input, Select, Spin } from "antd";
import { message } from "@/utils/antdMessage";

import { request } from "../../../api/request";
import { octopAgentsApi } from "../../../api/modules/octopAgents";
import {
  expertMarketApi,
  type MarketExpert,
} from "../../../api/modules/expertMarket";
import {
  publishedExpertsApi,
  type PublishedExpert,
} from "../../../api/modules/publishedExperts";
import { skillPackagesApi } from "../../../api/modules/skillPackages";
import type { SkillPackage } from "../../../api/types/skillPackage";
import { AgentAdvancedConfigFields } from "../../../components/AgentAdvancedConfigFields";
import ExpertColorPicker from "../../../components/ExpertColorPicker";
import { apiErrorMessage } from "../../../utils/apiError";
import {
  expertPaletteColor,
  parseStoredColor,
} from "../../../utils/expertColor";
import {
  DEFAULT_PALETTE,
  isCuratedPalette,
} from "../../../styles/themePalettes";
import {
  buildAgentRuntimeRequest,
  type AgentRuntimeFormValues,
} from "../../../utils/agentRuntimeConfig";
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
import {
  buildBackendSpec,
  DEFAULT_BACKEND,
  ensureBubblewrapAfterProbe,
  ensureBwrapMessage,
  ensureBwrapToastKind,
  probeRootDir,
  rootDirProbeMessage,
  shouldProbeRootDir,
  validatePathMappings,
  type PathMapping,
} from "./agentBackendForm";
import AgentBackendFields from "./AgentBackendFields";
import ExpertAvatarPicker from "./ExpertAvatarPicker";
import styles from "../index.module.less";

type FileContent = NamedFileContent;

interface ExpertDetail {
  file_contents?: FileContent[];
  welcome_message?: { zh?: string; en?: string };
}

export type CreateFromTemplateSource =
  | { kind: "builtin"; expert: ExpertSummary }
  | { kind: "published"; expert: PublishedExpert }
  | { kind: "market"; expert: MarketExpert };

interface CreateFromExpertDrawerProps {
  open: boolean;
  source: CreateFromTemplateSource | null;
  lang: "zh" | "en";
  onClose: () => void;
  onCreated: (agentId: string, agentName: string) => void;
}

function sourceTitle(
  source: CreateFromTemplateSource,
  lang: "zh" | "en",
): string {
  if (source.kind === "builtin") {
    return pickLocale(source.expert.label, lang) || source.expert.id;
  }
  if (source.kind === "published") {
    return source.expert.name;
  }
  return pickLocale(source.expert.label, lang) || source.expert.slug;
}

function sourceDefaults(
  source: CreateFromTemplateSource,
  lang: "zh" | "en",
): {
  name: string;
  description: string;
  color: string | null;
  welcome_message: string;
} {
  if (source.kind === "builtin") {
    return {
      name: pickLocale(source.expert.label, lang) || source.expert.id,
      description: pickLocale(source.expert.description, lang),
      color: source.expert.color ?? null,
      welcome_message: pickLocale(source.expert.welcome_message, lang),
    };
  }
  if (source.kind === "published") {
    return {
      name: source.expert.name,
      description: source.expert.description,
      color: source.expert.color ?? null,
      welcome_message: pickLocale(source.expert.welcome_message, lang),
    };
  }
  return {
    name: pickLocale(source.expert.label, lang) || source.expert.slug,
    description: pickLocale(source.expert.description, lang),
    color: source.expert.color ?? null,
    welcome_message: "",
  };
}

function sourceIcon(source: CreateFromTemplateSource | null): {
  iconUrl: string | null;
  iconName: string | null;
} {
  if (!source) return { iconUrl: null, iconName: null };
  if (source.kind === "builtin") {
    return { iconUrl: null, iconName: source.expert.icon_name ?? null };
  }
  if (source.kind === "published") {
    return { iconUrl: null, iconName: source.expert.icon_name };
  }
  return {
    iconUrl: source.expert.icon_url ?? null,
    iconName: source.expert.icon_name ?? null,
  };
}

export default function CreateFromExpertDrawer({
  open,
  source,
  lang,
  onClose,
  onCreated,
}: CreateFromExpertDrawerProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<
    {
      name: string;
      description: string;
      agent_id?: string;
      welcome_message?: string;
      default_model: string;
      backend_choice: string;
      composite_default: string;
      root_dir?: string;
      skill_package_ids?: string[];
    } & AgentRuntimeFormValues
  >();
  const [submitting, setSubmitting] = useState(false);

  const { models, modelsLoading, backends, backendsLoading } =
    useAgentFormResources(open && !!source);

  const [pathMappings, setPathMappings] = useState<PathMapping[]>([]);

  const [fileContents, setFileContents] = useState<FileContent[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [skillPackages, setSkillPackages] = useState<SkillPackage[]>([]);
  const [skillPackagesLoading, setSkillPackagesLoading] = useState(false);
  const [colorPalette, setColorPalette] = useState<string>("rose");
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);

  const backendChoice =
    Form.useWatch("backend_choice", form) ?? DEFAULT_BACKEND;

  const sourceKey = useMemo(() => {
    if (!source) return "";
    if (source.kind === "builtin") return `builtin:${source.expert.id}`;
    if (source.kind === "published") return `published:${source.expert.id}`;
    return `market:${source.expert.slug}`;
  }, [source]);

  useEffect(() => {
    if (!open || !source) return;
    let cancelled = false;

    setPathMappings([]);
    const defaults = sourceDefaults(source, lang);
    setColorPalette(parseStoredColor(defaults.color) ?? DEFAULT_PALETTE);
    setAvatarFile(null);
    setAvatarPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    form.setFieldsValue({
      name: defaults.name,
      description: defaults.description,
      agent_id: undefined,
      welcome_message: defaults.welcome_message,
      default_model: MODEL_AUTO_VALUE,
      backend_choice: DEFAULT_BACKEND,
      composite_default: DEFAULT_BACKEND,
      skill_package_ids: [],
    });

    if (source.kind === "market") {
      setFileContents([]);
      setDetailLoading(false);
      return;
    }

    setDetailLoading(true);
    const detailPath =
      source.kind === "builtin"
        ? `/experts/${encodeURIComponent(source.expert.id)}`
        : `/experts/published/${encodeURIComponent(source.expert.id)}`;
    request<ExpertDetail>(detailPath)
      .then((data) => {
        if (cancelled) return;
        setFileContents(data.file_contents ?? []);
        const welcome = data.welcome_message;
        const welcomeText = pickLocale(welcome, lang);
        if (welcomeText) {
          form.setFieldsValue({
            welcome_message: welcomeText,
          });
        }
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
  }, [open, source, sourceKey, lang, form]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setSkillPackagesLoading(true);
    skillPackagesApi
      .list()
      .then((packages) => {
        if (!cancelled) setSkillPackages(packages);
      })
      .catch(() => {
        if (!cancelled) setSkillPackages([]);
      })
      .finally(() => {
        if (!cancelled) setSkillPackagesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const handleCreate = async () => {
    if (!source) return;
    const values = await form.validateFields();
    const stored = form.getFieldsValue(true) as {
      welcome_message?: string;
    };
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
          `${rootDirProbeMessage(probe, t)}\n${t(
            "experts.rootDirProbe.guidance",
          )}`,
        );
        return;
      }
    }
    setSubmitting(true);
    let bwrapToast: { kind: "success" | "warning"; text: string } | null = null;
    try {
      if (shouldProbeRootDir(values.backend_choice, values.root_dir)) {
        const bwrap = await ensureBubblewrapAfterProbe();
        const kind = ensureBwrapToastKind(bwrap.status);
        if (kind !== "none") {
          bwrapToast = { kind, text: ensureBwrapMessage(bwrap, t) };
        }
      }

      const backendSpec = buildBackendSpec(
        values.backend_choice,
        values.composite_default ?? DEFAULT_BACKEND,
        pathMappings,
        values.root_dir,
      );

      const welcomeText = (stored.welcome_message ?? "").trim();
      const payload = {
        name: values.name,
        description: values.description || undefined,
        agent_id: values.agent_id?.trim() || undefined,
        default_model: defaultModelFromForm(values.default_model) ?? undefined,
        backend: backendSpec,
        skill_package_ids: values.skill_package_ids ?? [],
        color: isCuratedPalette(colorPalette)
          ? expertPaletteColor(colorPalette)
          : colorPalette,
        ...(welcomeText ? { welcome_message: welcomeText } : {}),
        ...buildAgentRuntimeRequest(values),
      };

      let body: { agent_id: string; name: string };
      if (source.kind === "builtin") {
        body = await request<{ agent_id: string; name: string }>(
          `/agents/from-expert/${encodeURIComponent(source.expert.id)}`,
          {
            method: "POST",
            body: JSON.stringify(payload),
          },
        );
      } else if (source.kind === "published") {
        body = await publishedExpertsApi.install(source.expert.id, payload);
      } else {
        const created = await expertMarketApi.install(
          source.expert.slug,
          payload,
        );
        body = { agent_id: created.agent_id, name: created.name };
        const enrichment = created.market?.welcome_enrichment;
        if (enrichment === "pending") {
          message.success(
            t("experts.marketCreateSuccessEnriching", { name: body.name }),
          );
        } else {
          message.success(
            t("experts.marketCreateSuccess", { name: body.name }),
          );
        }
      }

      if (source.kind !== "market") {
        message.success(t("experts.agentCreated", { name: body.name }));
      }
      if (avatarFile) {
        try {
          await octopAgentsApi.uploadAvatar(body.agent_id, avatarFile);
        } catch {
          message.warning(t("experts.avatarUploadLater"));
        }
      }
      if (bwrapToast?.kind === "success") {
        message.success(bwrapToast.text);
      } else if (bwrapToast?.kind === "warning") {
        message.warning(bwrapToast.text);
      }
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

  const { configFiles, skillGroups, subagentFiles } =
    groupExpertFiles(fileContents);
  const showFilePreview = source?.kind !== "market";

  const title = source
    ? t("experts.createDrawerTitle", {
        name: sourceTitle(source, lang),
      })
    : "";

  return (
    <Drawer
      open={open}
      title={title}
      width={520}
      onClose={onClose}
      destroyOnHidden
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

        <Form.Item
          name="agent_id"
          label={t("experts.customIdLabel")}
          extra={t("experts.customIdHint")}
          rules={[
            {
              validator: (_: unknown, value: string | undefined) => {
                const v = value?.trim() ?? "";
                if (!v) return Promise.resolve();
                if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{1,62}[a-zA-Z0-9]$/.test(v)) {
                  return Promise.reject(
                    new Error(t("experts.customIdInvalid")),
                  );
                }
                if (
                  ["api", "admin", "agents", "experts"].includes(
                    v.toLowerCase(),
                  )
                ) {
                  return Promise.reject(
                    new Error(t("experts.customIdReserved", { id: v })),
                  );
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <Input placeholder={t("experts.customIdPlaceholder")} allowClear />
        </Form.Item>

        <Form.Item name="description" label={t("experts.agentDescription")}>
          <Input.TextArea rows={2} />
        </Form.Item>

        <Form.Item
          name="welcome_message"
          label={t("experts.welcomeMessageTitle")}
          extra={t("experts.createWelcomeHint")}
        >
          <Input.TextArea
            rows={2}
            placeholder={t("experts.welcomeMessagePlaceholder")}
          />
        </Form.Item>

        <Form.Item label={t("experts.avatar")}>
          <ExpertAvatarPicker
            iconUrl={avatarPreview ?? sourceIcon(source).iconUrl}
            iconName={sourceIcon(source).iconName}
            color={
              isCuratedPalette(colorPalette)
                ? expertPaletteColor(colorPalette)
                : colorPalette
            }
            disabled={submitting}
            onPick={(file) => {
              setAvatarFile(file);
              setAvatarPreview((prev) => {
                if (prev) URL.revokeObjectURL(prev);
                return URL.createObjectURL(file);
              });
            }}
            onRemove={
              avatarPreview
                ? () => {
                    setAvatarFile(null);
                    setAvatarPreview((prev) => {
                      if (prev) URL.revokeObjectURL(prev);
                      return null;
                    });
                  }
                : undefined
            }
          />
        </Form.Item>

        <Form.Item label={t("experts.color")} extra={t("experts.colorHint")}>
          <ExpertColorPicker value={colorPalette} onChange={setColorPalette} />
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

        <Form.Item
          name="skill_package_ids"
          label={t("experts.skillPackagesLabel")}
          extra={t("experts.skillPackagesHint")}
        >
          <Select
            mode="multiple"
            allowClear
            loading={skillPackagesLoading}
            options={skillPackages.map((pack) => ({
              value: pack.id,
              label: pack.name,
            }))}
            placeholder={t("experts.skillPackagesPlaceholder")}
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

        <Collapse
          ghost
          items={[
            {
              key: "advanced",
              label: t("experts.advancedOptions"),
              children: <AgentAdvancedConfigFields />,
            },
          ]}
        />
      </Form>

      {showFilePreview &&
        (detailLoading ? (
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
                    label: (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "baseline",
                          gap: 8,
                        }}
                      >
                        <span style={{ fontWeight: 500 }}>
                          {group.emoji} {group.displayName}
                        </span>
                        <span
                          style={{
                            fontSize: 11,
                            color:
                              "var(--fn-text-quaternary, var(--fn-text-tertiary))",
                          }}
                        >
                          skills/{group.name}/
                        </span>
                      </span>
                    ),
                    children: (
                      <>
                        {group.description ? (
                          <p
                            style={{
                              fontSize: 12,
                              color: "var(--fn-text-secondary)",
                              margin: "0 0 8px",
                            }}
                          >
                            {group.description}
                          </p>
                        ) : null}
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
                                    background:
                                      "var(--fn-bg-secondary, #f5f5f5)",
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
                      </>
                    ),
                  }))}
                />
              )}
            </div>

            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>
                {t("experts.subagentFilesTitle", {
                  count: subagentFiles.length,
                })}
              </div>
              <p
                style={{
                  fontSize: 12,
                  color: "var(--fn-text-tertiary)",
                  margin: "0 0 8px",
                }}
              >
                {t("experts.subagentTemplateHint")}
              </p>
              {subagentFiles.length === 0 ? (
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--fn-text-tertiary)",
                    padding: "4px 0",
                  }}
                >
                  {t("experts.noSubagentFiles")}
                </div>
              ) : (
                <Collapse
                  size="small"
                  items={subagentFiles.map((subagent) => ({
                    key: subagent.slug,
                    label: (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "baseline",
                          gap: 8,
                        }}
                      >
                        <span style={{ fontWeight: 500 }}>
                          {subagent.emoji} {subagent.name}
                        </span>
                        <span
                          style={{
                            fontSize: 11,
                            color:
                              "var(--fn-text-quaternary, var(--fn-text-tertiary))",
                          }}
                        >
                          agents/{subagent.slug}.md
                        </span>
                      </span>
                    ),
                    children: (
                      <>
                        {subagent.description ? (
                          <p
                            style={{
                              fontSize: 12,
                              color: "var(--fn-text-secondary)",
                              margin: "0 0 8px",
                            }}
                          >
                            {subagent.description}
                          </p>
                        ) : null}
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
                          {subagent.file.content}
                        </pre>
                      </>
                    ),
                  }))}
                />
              )}
            </div>
          </>
        ))}
    </Drawer>
  );
}
