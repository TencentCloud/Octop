// dashboard/src/pages/Experts/components/EditAgentDrawer.tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  Collapse,
  Drawer,
  Dropdown,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Spin,
  message,
} from "antd";
import { MoreHorizontal } from "lucide-react";
import { request } from "../../../api/request";
import { workspaceApi } from "../../../api/modules/workspace";
import { apiErrorMessage } from "../../../utils/apiError";
import { isAgentChatReady } from "../../../utils/agentError";
import { useAgentFormResources } from "../../../hooks/useAgentFormResources";
import type { OctopAgent } from "../../../context/AgentContext";
import WorkspaceDrawer from "../../Agent/Workspace/components/WorkspaceDrawer";
import {
  buildModelSelectOptions,
  defaultModelFromForm,
  defaultModelToForm,
} from "../../../utils/modelOptions";
import { metaForFile } from "./iconForName";
import { useSkillDisplayName } from "../../Agent/Skills/skillDisplayNames";
import FileEditModal from "./FileEditModal";
import { fetchConfigMdFiles } from "./expertFileGroups";
import {
  buildBackendSpec,
  DEFAULT_BACKEND,
  parseBackendSpec,
  probeRootDir,
  rootDirProbeMessage,
  shouldProbeRootDir,
  validatePathMappings,
  type PathMapping,
} from "./agentBackendForm";
import AgentBackendFields from "./AgentBackendFields";
import SubagentCatalogDrawer from "./SubagentCatalogDrawer";
import styles from "../index.module.less";

interface AgentDetail {
  id: string;
  name: string;
  description: string | null;
  default_model: string | null;
  config?: Record<string, unknown>;
}

interface SkillSummary {
  slug?: string;
  name: string;
  description?: string;
  enabled?: boolean;
  kind?: "builtin" | "workspace";
}

interface SubagentSummary {
  slug: string;
  name: string;
  description?: string;
  path: string;
  emoji?: string;
}

function workspaceSkills(skills: SkillSummary[]): SkillSummary[] {
  return skills.filter((s) => s.kind !== "builtin");
}

function subagentFilePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

interface EditFormValues {
  name: string;
  description: string;
  default_model: string;
  backend_choice: string;
  composite_default: string;
  root_dir?: string;
  max_iters?: number;
  max_input_length?: number;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
}

interface EditAgentDrawerProps {
  open: boolean;
  agent: OctopAgent | null;
  onClose: () => void;
  onSaved: (
    updated: Pick<
      OctopAgent,
      "agent_id" | "name" | "description" | "default_model"
    >,
  ) => void;
}

function readNumber(
  cfg: Record<string, unknown>,
  key: string,
): number | undefined {
  const value = cfg[key];
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

interface EditAgentDrawerBodyProps {
  agent: OctopAgent;
  onClose: () => void;
  onSaved: EditAgentDrawerProps["onSaved"];
  onSaveReady: (save: () => Promise<void>) => void;
  onSavingChange: (saving: boolean) => void;
}

function EditAgentDrawerBody({
  agent,
  onClose,
  onSaved,
  onSaveReady,
  onSavingChange,
}: EditAgentDrawerBodyProps) {
  const { t } = useTranslation();
  const skillDisplayName = useSkillDisplayName();
  const [workspaceDrawerOpen, setWorkspaceDrawerOpen] = useState(false);
  const [form] = Form.useForm<EditFormValues>();
  const [workspaceFiles, setWorkspaceFiles] = useState<string[]>([]);
  const [agentSkills, setAgentSkills] = useState<SkillSummary[]>([]);
  const [agentSubagents, setAgentSubagents] = useState<SubagentSummary[]>([]);
  const { models, modelsLoading, backends, backendsLoading } =
    useAgentFormResources(true);
  const [pathMappings, setPathMappings] = useState<PathMapping[]>([]);
  const [agentConfig, setAgentConfig] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [filesLoading, setFilesLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fileModalOpen, setFileModalOpen] = useState(false);
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [listRenameOpen, setListRenameOpen] = useState(false);
  const [listRenamePath, setListRenamePath] = useState<string | null>(null);
  const [listRenameValue, setListRenameValue] = useState("");
  const [listRenameKind, setListRenameKind] = useState<"config" | "subagent">(
    "config",
  );
  const [listRenameSaving, setListRenameSaving] = useState(false);
  const [subagentCatalogOpen, setSubagentCatalogOpen] = useState(false);

  const installedSubagentSlugs = useMemo(
    () => new Set(agentSubagents.map((s) => s.slug)),
    [agentSubagents],
  );

  const backendChoice =
    Form.useWatch("backend_choice", form) ?? DEFAULT_BACKEND;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPathMappings([]);
    setAgentConfig({});

    const load = async () => {
      try {
        const ag = await request<AgentDetail>(`/agents/${agent.agent_id}`);
        if (cancelled) return;

        const cfg = ag.config ?? {};
        setAgentConfig(cfg);
        const parsedBackend = parseBackendSpec(cfg.backend);
        setPathMappings(parsedBackend.pathMappings);

        form.setFieldsValue({
          name: ag.name,
          description: ag.description ?? "",
          default_model: defaultModelToForm(ag.default_model),
          backend_choice: parsedBackend.backendChoice,
          composite_default: parsedBackend.compositeDefault,
          root_dir: parsedBackend.rootDir,
          max_iters: readNumber(cfg, "max_iters"),
          max_input_length: readNumber(cfg, "max_input_length"),
          temperature: readNumber(cfg, "temperature"),
          top_p: readNumber(cfg, "top_p"),
          max_tokens: readNumber(cfg, "max_tokens"),
        });
        setLoading(false);

        if (isAgentChatReady(agent.state)) {
          setFilesLoading(true);
          void fetchConfigMdFiles(agent.agent_id)
            .then((files) => {
              if (!cancelled) setWorkspaceFiles(files);
            })
            .catch((err: unknown) => {
              if (!cancelled) {
                setWorkspaceFiles([]);
                message.warning(
                  err instanceof Error
                    ? err.message
                    : t("experts.workspaceFilesFailed"),
                );
              }
            })
            .finally(() => {
              if (!cancelled) setFilesLoading(false);
            });

          void request<SkillSummary[]>(`/agents/${agent.agent_id}/skills`)
            .then((skills) => {
              if (!cancelled) setAgentSkills(workspaceSkills(skills));
            })
            .catch(() => {
              if (!cancelled) setAgentSkills([]);
            });

          void request<SubagentSummary[]>(`/agents/${agent.agent_id}/subagents`)
            .then((subagents) => {
              if (!cancelled) setAgentSubagents(subagents);
            })
            .catch(() => {
              if (!cancelled) setAgentSubagents([]);
            });
        }
      } catch {
        message.error(t("experts.loadDetailFailed"));
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [agent.agent_id, agent.state, form, t]);

  const handleSave = useCallback(async () => {
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
    setSaving(true);
    try {
      const backendSpec = buildBackendSpec(
        values.backend_choice,
        values.composite_default ?? DEFAULT_BACKEND,
        pathMappings,
        values.root_dir,
      );

      const nextConfig: Record<string, unknown> = {
        ...agentConfig,
        backend: backendSpec,
      };

      const optionalNumbers: Array<[keyof EditFormValues, string]> = [
        ["max_iters", "max_iters"],
        ["max_input_length", "max_input_length"],
        ["temperature", "temperature"],
        ["top_p", "top_p"],
        ["max_tokens", "max_tokens"],
      ];
      for (const [formKey, cfgKey] of optionalNumbers) {
        const val = values[formKey];
        if (typeof val === "number" && Number.isFinite(val)) {
          nextConfig[cfgKey] = val;
        } else {
          delete nextConfig[cfgKey];
        }
      }

      await request(`/agents/${agent.agent_id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: values.name,
          description: values.description || null,
          default_model: defaultModelFromForm(values.default_model),
          config: nextConfig,
        }),
      });
      message.success(t("common.save") + " ✓");
      const defaultModel = defaultModelFromForm(values.default_model);
      onSaved({
        agent_id: agent.agent_id,
        name: values.name,
        description: values.description || null,
        default_model: defaultModel,
      });
      onClose();
    } catch (err) {
      message.error(apiErrorMessage(err, t("experts.patchFailed"), t));
    } finally {
      setSaving(false);
    }
  }, [agent.agent_id, agentConfig, form, onClose, onSaved, pathMappings, t]);

  useEffect(() => {
    onSaveReady(handleSave);
  }, [handleSave, onSaveReady]);

  useEffect(() => {
    onSavingChange(saving);
  }, [onSavingChange, saving]);

  const openFileEditor = (filePath: string) => {
    setEditingFile(filePath.startsWith("/") ? filePath : `/${filePath}`);
    setFileModalOpen(true);
  };

  const displayName = (path: string) => path.replace(/^\//, "");

  const reloadConfigFiles = useCallback(async () => {
    setFilesLoading(true);
    try {
      const files = await fetchConfigMdFiles(agent.agent_id);
      setWorkspaceFiles(files);
    } catch {
      setWorkspaceFiles([]);
    } finally {
      setFilesLoading(false);
    }
  }, [agent.agent_id]);

  const reloadSkills = useCallback(async () => {
    try {
      const skills = await request<SkillSummary[]>(
        `/agents/${agent.agent_id}/skills`,
      );
      setAgentSkills(workspaceSkills(skills));
    } catch {
      setAgentSkills([]);
    }
  }, [agent.agent_id]);

  const reloadSubagents = useCallback(async () => {
    try {
      const subagents = await request<SubagentSummary[]>(
        `/agents/${agent.agent_id}/subagents`,
      );
      setAgentSubagents(subagents);
    } catch {
      setAgentSubagents([]);
    }
  }, [agent.agent_id]);

  const joinWorkspacePath = (dir: string, name: string) => {
    const base = dir.endsWith("/") ? dir.slice(0, -1) : dir;
    if (!base || base === "/") return `/${name}`;
    return `${base}/${name}`;
  };

  const parentWorkspacePath = (path: string) => {
    const parts = path.split("/").filter(Boolean);
    parts.pop();
    return parts.length ? `/${parts.join("/")}` : "/";
  };

  const confirmDeleteConfigFile = (path: string) => {
    Modal.confirm({
      title: t("workspace.deleteConfirm"),
      okText: t("common.delete"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        await workspaceApi.deleteWorkspaceFile(agent.agent_id, path);
        message.success(t("workspace.deleteSuccess"));
        await reloadConfigFiles();
      },
    });
  };

  const confirmDeleteSkill = (skill: SkillSummary) => {
    const slug = skill.slug ?? skill.name;
    Modal.confirm({
      title: t("skills.deleteConfirmContent", { slug }),
      okText: t("common.delete"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        await request(`/agents/${agent.agent_id}/skills/${slug}`, {
          method: "DELETE",
        });
        message.success(t("skills.deleteSuccess"));
        await reloadSkills();
      },
    });
  };

  const confirmDeleteSubagent = (subagent: SubagentSummary) => {
    Modal.confirm({
      title: t("workspace.deleteConfirm"),
      okText: t("common.delete"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        await workspaceApi.deleteWorkspaceFile(
          agent.agent_id,
          subagentFilePath(subagent.path),
        );
        message.success(t("workspace.deleteSuccess"));
        await reloadSubagents();
      },
    });
  };

  const openListRename = (path: string, kind: "config" | "subagent") => {
    setListRenamePath(path);
    setListRenameValue(path.split("/").filter(Boolean).pop() ?? "");
    setListRenameKind(kind);
    setListRenameOpen(true);
  };

  const confirmListRename = async () => {
    if (!listRenamePath || !listRenameValue.trim()) return;
    const dest = joinWorkspacePath(
      parentWorkspacePath(listRenamePath),
      listRenameValue.trim(),
    );
    if (dest === listRenamePath) {
      setListRenameOpen(false);
      return;
    }
    setListRenameSaving(true);
    try {
      await workspaceApi.moveWorkspaceFile(
        agent.agent_id,
        listRenamePath,
        dest,
      );
      if (listRenameKind === "subagent") {
        await request(`/agents/${agent.agent_id}/reload`, { method: "POST" });
      }
      message.success(t("workspace.renameSuccess"));
      setListRenameOpen(false);
      if (listRenameKind === "config") {
        await reloadConfigFiles();
      } else {
        await reloadSubagents();
      }
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("workspace.renameFailed"), t));
    } finally {
      setListRenameSaving(false);
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

  return (
    <>
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 40 }}>
          <Spin />
        </div>
      ) : (
        <>
          <div className={styles.drawerSection}>
            <div className={styles.drawerSectionTitle}>
              {t("experts.basicInfo")}
            </div>
            <Form form={form} layout="vertical" size="middle">
              <Form.Item
                name="name"
                label={t("experts.agentName")}
                rules={[
                  { required: true, message: t("experts.pleaseEnterName") },
                ]}
              >
                <Input />
              </Form.Item>
              <Form.Item
                name="description"
                label={t("experts.agentDescription")}
              >
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item
                name="default_model"
                label={t("experts.defaultModelLabel")}
              >
                <Select
                  loading={modelsLoading}
                  placeholder={t("experts.defaultModelPlaceholder")}
                  options={buildModelSelectOptions(
                    models,
                    t("experts.defaultModelAuto"),
                  )}
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

              <Collapse
                ghost
                items={[
                  {
                    key: "advanced",
                    label: t("experts.advancedOptions"),
                    children: (
                      <>
                        <Form.Item
                          name="max_iters"
                          label={t("agentConfig.maxIters")}
                          tooltip={t("agentConfig.maxItersTooltip")}
                        >
                          <InputNumber
                            min={1}
                            style={{ width: "100%" }}
                            placeholder={t("agentConfig.maxItersPlaceholder")}
                          />
                        </Form.Item>
                        <Form.Item
                          name="max_input_length"
                          label={t("agentConfig.maxInputLength")}
                          tooltip={t("agentConfig.maxInputLengthTooltip")}
                        >
                          <InputNumber
                            min={1000}
                            step={1024}
                            style={{ width: "100%" }}
                            placeholder={t(
                              "agentConfig.maxInputLengthPlaceholder",
                            )}
                          />
                        </Form.Item>
                        <Form.Item
                          name="temperature"
                          label={t("experts.temperature")}
                          tooltip={t("experts.temperatureTooltip")}
                        >
                          <InputNumber
                            min={0}
                            max={2}
                            step={0.1}
                            style={{ width: "100%" }}
                          />
                        </Form.Item>
                        <Form.Item
                          name="top_p"
                          label={t("experts.topP")}
                          tooltip={t("experts.topPTooltip")}
                        >
                          <InputNumber
                            min={0}
                            max={1}
                            step={0.05}
                            style={{ width: "100%" }}
                          />
                        </Form.Item>
                        <Form.Item
                          name="max_tokens"
                          label={t("experts.maxTokens")}
                          tooltip={t("experts.maxTokensTooltip")}
                        >
                          <InputNumber min={1} style={{ width: "100%" }} />
                        </Form.Item>
                      </>
                    ),
                  },
                ]}
              />
            </Form>
          </div>

          {isAgentChatReady(agent.state) && (
            <div className={styles.drawerSection}>
              <Collapse
                ghost
                defaultActiveKey={["configFiles"]}
                style={{ margin: "-4px 0 0" }}
                items={[
                  {
                    key: "configFiles",
                    label: (
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <span>
                          {t("experts.configFiles", {
                            count: workspaceFiles.length,
                          })}
                        </span>
                        <Button
                          type="link"
                          size="small"
                          style={{ padding: 0, height: "auto" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setWorkspaceDrawerOpen(true);
                          }}
                        >
                          {t("experts.openWorkspace")}
                        </Button>
                      </div>
                    ),
                    children: (
                      <div className={styles.fileList}>
                        {filesLoading ? (
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "center",
                              padding: "16px 0",
                            }}
                          >
                            <Spin size="small" />
                          </div>
                        ) : workspaceFiles.length === 0 ? (
                          <div
                            style={{
                              fontSize: 13,
                              color: "var(--fn-text-tertiary)",
                              padding: "8px 0",
                            }}
                          >
                            {t("experts.noWorkspaceFiles")}
                          </div>
                        ) : (
                          workspaceFiles.map((file) => {
                            const basename = displayName(file);
                            const meta = metaForFile(basename, t);
                            return (
                              <div key={file} className={styles.fileItem}>
                                <button
                                  type="button"
                                  className={styles.fileItemMain}
                                  onClick={() => openFileEditor(file)}
                                >
                                  <div
                                    className={styles.fileIcon}
                                    style={{
                                      color: meta.color,
                                      background: `${meta.color}1a`,
                                    }}
                                  >
                                    {meta.icon}
                                  </div>
                                  <div className={styles.fileMeta}>
                                    <div className={styles.fileLabel}>
                                      {meta.label}
                                    </div>
                                    <div className={styles.filePath}>
                                      {basename}
                                    </div>
                                  </div>
                                  <span className={styles.fileHint}>
                                    {t("experts.editFile")}
                                  </span>
                                </button>
                                <Dropdown
                                  menu={{
                                    items: [
                                      {
                                        key: "rename",
                                        label: t("workspace.rename"),
                                        onClick: () =>
                                          openListRename(file, "config"),
                                      },
                                      {
                                        key: "delete",
                                        label: t("common.delete"),
                                        danger: true,
                                        onClick: () =>
                                          confirmDeleteConfigFile(file),
                                      },
                                    ],
                                  }}
                                  trigger={["click"]}
                                >
                                  <button
                                    type="button"
                                    className={styles.fileItemMenu}
                                    aria-label={t("workspace.rename")}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <MoreHorizontal size={16} />
                                  </button>
                                </Dropdown>
                              </div>
                            );
                          })
                        )}
                      </div>
                    ),
                  },
                  {
                    key: "skills",
                    label: t("experts.skillFilesTitle", {
                      count: agentSkills.length,
                    }),
                    children: (
                      <>
                        <p
                          style={{
                            fontSize: 12,
                            color: "var(--fn-text-tertiary)",
                            margin: "0 0 8px",
                          }}
                        >
                          {t("experts.skillFilesHint")}
                        </p>
                        <div className={styles.fileList}>
                          {agentSkills.length === 0 ? (
                            <div
                              style={{
                                fontSize: 13,
                                color: "var(--fn-text-tertiary)",
                                padding: "8px 0",
                              }}
                            >
                              {t("experts.noSkillFiles")}
                            </div>
                          ) : (
                            agentSkills.map((skill) => (
                              <div
                                key={skill.slug ?? skill.name}
                                className={styles.fileItem}
                              >
                                <button
                                  type="button"
                                  className={styles.fileItemMain}
                                  onClick={() =>
                                    openFileEditor(
                                      `/skills/${
                                        skill.slug ?? skill.name
                                      }/SKILL.md`,
                                    )
                                  }
                                >
                                  <div
                                    className={styles.fileIcon}
                                    style={{
                                      color: "#059669",
                                      background: "#0596691a",
                                    }}
                                  >
                                    ⚡
                                  </div>
                                  <div className={styles.fileMeta}>
                                    <div className={styles.fileLabel}>
                                      {skillDisplayName(skill)}
                                    </div>
                                    <div className={styles.filePath}>
                                      {skill.description || "SKILL.md"}
                                    </div>
                                  </div>
                                  <span className={styles.fileHint}>
                                    {t("experts.editFile")}
                                  </span>
                                </button>
                                <Dropdown
                                  menu={{
                                    items: [
                                      {
                                        key: "delete",
                                        label: t("common.delete"),
                                        danger: true,
                                        onClick: () =>
                                          confirmDeleteSkill(skill),
                                      },
                                    ],
                                  }}
                                  trigger={["click"]}
                                >
                                  <button
                                    type="button"
                                    className={styles.fileItemMenu}
                                    aria-label={t("common.delete")}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <MoreHorizontal size={16} />
                                  </button>
                                </Dropdown>
                              </div>
                            ))
                          )}
                        </div>
                      </>
                    ),
                  },
                  {
                    key: "subagents",
                    label: (
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <span>
                          {t("experts.subagentFilesTitle", {
                            count: agentSubagents.length,
                          })}
                        </span>
                        <Button
                          type="link"
                          size="small"
                          style={{ padding: 0, height: "auto" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSubagentCatalogOpen(true);
                          }}
                        >
                          {t("experts.manageSubagents")}
                        </Button>
                      </div>
                    ),
                    children: (
                      <>
                        <p
                          style={{
                            fontSize: 12,
                            color: "var(--fn-text-tertiary)",
                            margin: "0 0 8px",
                          }}
                        >
                          {t("experts.subagentFilesHint")}
                        </p>
                        <div className={styles.fileList}>
                          {agentSubagents.length === 0 ? (
                            <div
                              style={{
                                fontSize: 13,
                                color: "var(--fn-text-tertiary)",
                                padding: "8px 0",
                              }}
                            >
                              {t("experts.noSubagentFiles")}
                            </div>
                          ) : (
                            agentSubagents.map((subagent) => (
                              <div
                                key={subagent.slug}
                                className={styles.fileItem}
                              >
                                <button
                                  type="button"
                                  className={styles.fileItemMain}
                                  onClick={() =>
                                    openFileEditor(
                                      subagentFilePath(subagent.path),
                                    )
                                  }
                                >
                                  <div
                                    className={styles.fileIcon}
                                    style={{
                                      color: "#6366f1",
                                      background: "#6366f11a",
                                    }}
                                  >
                                    {subagent.emoji ?? "🤖"}
                                  </div>
                                  <div className={styles.fileMeta}>
                                    <div className={styles.fileLabel}>
                                      {subagent.name}
                                    </div>
                                    <div className={styles.filePath}>
                                      {subagent.description ||
                                        subagent.path.replace(/^\//, "")}
                                    </div>
                                  </div>
                                  <span className={styles.fileHint}>
                                    {t("experts.editFile")}
                                  </span>
                                </button>
                                <Dropdown
                                  menu={{
                                    items: [
                                      {
                                        key: "rename",
                                        label: t("workspace.rename"),
                                        onClick: () =>
                                          openListRename(
                                            subagentFilePath(subagent.path),
                                            "subagent",
                                          ),
                                      },
                                      {
                                        key: "delete",
                                        label: t("common.delete"),
                                        danger: true,
                                        onClick: () =>
                                          confirmDeleteSubagent(subagent),
                                      },
                                    ],
                                  }}
                                  trigger={["click"]}
                                >
                                  <button
                                    type="button"
                                    className={styles.fileItemMenu}
                                    aria-label={t("workspace.rename")}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <MoreHorizontal size={16} />
                                  </button>
                                </Dropdown>
                              </div>
                            ))
                          )}
                        </div>
                      </>
                    ),
                  },
                ]}
              />
            </div>
          )}
        </>
      )}
      <WorkspaceDrawer
        agentId={agent.agent_id}
        open={workspaceDrawerOpen}
        onClose={() => setWorkspaceDrawerOpen(false)}
      />
      <SubagentCatalogDrawer
        agentId={agent.agent_id}
        agentState={agent.state}
        open={subagentCatalogOpen}
        installedSlugs={installedSubagentSlugs}
        onClose={() => setSubagentCatalogOpen(false)}
        onInstalled={() => {
          void reloadSubagents();
        }}
      />
      <Modal
        title={t("workspace.rename")}
        open={listRenameOpen}
        onCancel={() => {
          if (!listRenameSaving) setListRenameOpen(false);
        }}
        onOk={() => void confirmListRename()}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
        confirmLoading={listRenameSaving}
      >
        <Input
          value={listRenameValue}
          onChange={(e) => setListRenameValue(e.target.value)}
          onPressEnter={() => void confirmListRename()}
          autoFocus
        />
      </Modal>
      <FileEditModal
        open={fileModalOpen}
        agentId={agent.agent_id}
        filePath={editingFile}
        onClose={() => setFileModalOpen(false)}
        onSaved={() => {
          /* file saved */
        }}
      />
    </>
  );
}

export default function EditAgentDrawer({
  open,
  agent,
  onClose,
  onSaved,
}: EditAgentDrawerProps) {
  const { t } = useTranslation();
  const saveRef = useRef<(() => Promise<void>) | null>(null);
  const [saving, setSaving] = useState(false);

  const handleSaveReady = useCallback((save: () => Promise<void>) => {
    saveRef.current = save;
  }, []);

  return (
    <Drawer
      open={open}
      title={t("experts.editExpert")}
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
            onClick={() => void saveRef.current?.()}
            disabled={saving}
          >
            {saving ? t("experts.creating") : t("common.save")}
          </button>
        </div>
      }
    >
      {open && agent ? (
        <EditAgentDrawerBody
          agent={agent}
          onClose={onClose}
          onSaved={onSaved}
          onSaveReady={handleSaveReady}
          onSavingChange={setSaving}
        />
      ) : null}
    </Drawer>
  );
}
