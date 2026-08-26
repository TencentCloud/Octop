// dashboard/src/pages/Experts/components/EditAgentDrawer.tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Alert,
  App,
  Button,
  Collapse,
  Drawer,
  Dropdown,
  Form,
  Input,
  Modal,
  Select,
  Spin,
  Switch,
} from "antd";

import { MoreHorizontal } from "lucide-react";
import { request } from "../../../api/request";
import { AgentAdvancedConfigFields } from "../../../components/AgentAdvancedConfigFields";
import ExpertColorPicker from "../../../components/ExpertColorPicker";
import { workspaceApi } from "../../../api/modules/workspace";
import { skillPackagesApi } from "../../../api/modules/skillPackages";
import { apiErrorMessage, isNotFoundApiError } from "../../../utils/apiError";
import { isAgentChatReady } from "../../../utils/agentError";
import { useAgentFormResources } from "../../../hooks/useAgentFormResources";
import { octopAgentsApi } from "../../../api/modules/octopAgents";
import { useAgent, type OctopAgent } from "../../../context/AgentContext";
import ExpertAvatarPicker from "./ExpertAvatarPicker";
import WorkspaceDrawer from "../../Agent/Workspace/components/WorkspaceDrawer";
import {
  buildModelSelectOptions,
  defaultModelFromForm,
  defaultModelToForm,
} from "../../../utils/modelOptions";
import {
  expertPaletteColor,
  parseStoredColor,
} from "../../../utils/expertColor";
import {
  DEFAULT_PALETTE,
  isCuratedPalette,
} from "../../../styles/themePalettes";
import { metaForFile } from "./iconForName";
import {
  buildAgentRuntimeRequest,
  omitAgentRuntimeConfig,
  readAgentRuntimeFormValues,
} from "../../../utils/agentRuntimeConfig";
import { useSkillDisplayName } from "../../Agent/Skills/skillDisplayNames";
import FileEditModal from "./FileEditModal";
import WelcomeConfig, { type WelcomeConfigRef } from "./WelcomeConfig";
import {
  mergeWelcomeIntoManifest,
  parseManifestObject,
  shouldWriteWelcomeManifest,
  type WelcomeConfigData,
} from "./welcomeManifest";
import { fetchConfigMdFiles } from "./expertFileGroups";
import {
  buildBackendSpec,
  DEFAULT_BACKEND,
  ensureBubblewrapAfterProbe,
  ensureBwrapMessage,
  ensureBwrapToastKind,
  parseBackendSpec,
  probeRootDir,
  rootDirProbeMessage,
  shouldProbeRootDir,
  supportsHostSkillPackages,
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
  color?: string | null;
  icon_url?: string | null;
  max_iters?: number | null;
  max_input_length?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  welcome_message?: string | null;
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
  welcome_message?: string;
  is_shared?: boolean;
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
      | "agent_id"
      | "name"
      | "description"
      | "default_model"
      | "is_shared"
      | "color"
      | "icon_url"
    >,
  ) => void;
}

interface EditAgentDrawerBodyProps {
  agent: OctopAgent;
  onClose: () => void;
  onSaved: EditAgentDrawerProps["onSaved"];
  onSaveReady: (save: () => Promise<void>) => void;
  onSavingChange: (saving: boolean) => void;
}

/**
 * Merge page-config fields into the existing workspace .octop/manifest.json.
 * Missing file → start from {}. Invalid JSON is refused so we do not
 * clobber a hand-edited manifest.
 */
async function persistWelcomeManifest(
  agentId: string,
  data: WelcomeConfigData,
): Promise<"ok" | "invalid-json"> {
  let existing: Record<string, unknown> = {};
  try {
    const file = await workspaceApi.readWorkspaceFile(
      agentId,
      "/.octop/manifest.json",
    );
    const parsed = parseManifestObject(file.content ?? "");
    if (!parsed.ok) return "invalid-json";
    existing = parsed.value;
  } catch (err) {
    if (!isNotFoundApiError(err)) throw err;
    // Legacy agents may still keep welcome metadata at workspace root.
    try {
      const legacy = await workspaceApi.readWorkspaceFile(
        agentId,
        "/manifest.json",
      );
      const parsed = parseManifestObject(legacy.content ?? "");
      if (!parsed.ok) return "invalid-json";
      existing = parsed.value;
    } catch (legacyErr) {
      if (!isNotFoundApiError(legacyErr)) throw legacyErr;
    }
  }
  const merged = mergeWelcomeIntoManifest(existing, data);
  await workspaceApi.createWorkspaceFile(
    agentId,
    "/.octop/manifest.json",
    JSON.stringify(merged, null, 2),
  );
  return "ok";
}

function EditAgentDrawerBody({
  agent,
  onClose,
  onSaved,
  onSaveReady,
  onSavingChange,
}: EditAgentDrawerBodyProps) {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();
  const { refresh } = useAgent();
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
  const [colorPalette, setColorPalette] = useState<string>(
    () => parseStoredColor(agent.color) ?? DEFAULT_PALETTE,
  );
  const [iconUrl, setIconUrl] = useState<string | null>(agent.icon_url);
  const [avatarBusy, setAvatarBusy] = useState(false);
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
  const welcomeConfigRef = useRef<WelcomeConfigRef>(null);

  const installedSubagentSlugs = useMemo(
    () => new Set(agentSubagents.map((s) => s.slug)),
    [agentSubagents],
  );

  const backendChoice =
    Form.useWatch("backend_choice", form) ?? DEFAULT_BACKEND;
  const watchedRootDir = Form.useWatch("root_dir", form);
  const workspaceDirFromConfig =
    typeof agentConfig.workspace_dir === "string"
      ? agentConfig.workspace_dir
      : null;
  const skillPackagesSupported = supportsHostSkillPackages({
    backendChoice,
    rootDir: watchedRootDir,
    workspaceDir: workspaceDirFromConfig,
  });

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
        const colorFromRow =
          typeof ag.color === "string"
            ? ag.color
            : typeof cfg.color === "string"
            ? cfg.color
            : agent.color ?? null;
        setColorPalette(parseStoredColor(colorFromRow) ?? DEFAULT_PALETTE);
        setIconUrl(
          typeof ag.icon_url === "string" && ag.icon_url.trim()
            ? ag.icon_url
            : null,
        );
        const parsedBackend = parseBackendSpec(cfg.backend);
        setPathMappings(parsedBackend.pathMappings);

        form.setFieldsValue({
          name: ag.name,
          description: ag.description ?? "",
          welcome_message:
            typeof ag.welcome_message === "string" ? ag.welcome_message : "",
          is_shared: agent.is_shared ?? false,
          default_model: defaultModelToForm(ag.default_model),
          backend_choice: parsedBackend.backendChoice,
          composite_default: parsedBackend.compositeDefault,
          root_dir: parsedBackend.rootDir,
          ...readAgentRuntimeFormValues(ag),
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
          `${rootDirProbeMessage(probe, t)}\n${t(
            "experts.rootDirProbe.guidance",
          )}`,
        );
        return;
      }
    }
    setSaving(true);
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

      const nextColor = isCuratedPalette(colorPalette)
        ? expertPaletteColor(colorPalette)
        : colorPalette;
      const nextConfig = omitAgentRuntimeConfig({
        ...agentConfig,
        backend: backendSpec,
      });
      delete nextConfig.color;
      delete nextConfig.icon_name;
      delete nextConfig.icon_url;
      delete nextConfig.expert_id;
      delete nextConfig.skill_package_ids;
      delete nextConfig.published_expert_id;
      delete nextConfig.welcome_message;

      // Persist page config before PATCH. Workspace I/O survives the
      // background harness reload; skip when the editor is still loading
      // or the user never touched 页面配置, so a name/model save cannot
      // clobber bilingual copy or extra manifest keys.
      const welcomeSnap = welcomeConfigRef.current?.getSnapshot();
      if (
        welcomeSnap &&
        isAgentChatReady(agent.state) &&
        shouldWriteWelcomeManifest(welcomeSnap.status, welcomeSnap.dirty)
      ) {
        try {
          const result = await persistWelcomeManifest(
            agent.agent_id,
            welcomeSnap.data,
          );
          if (result === "invalid-json") {
            message.warning(t("experts.manifestInvalidJson"));
          }
        } catch (manifestErr) {
          message.warning(
            apiErrorMessage(manifestErr, t("experts.manifestWriteFailed"), t),
          );
        }
      }

      const stored = form.getFieldsValue(true) as EditFormValues;
      await request(`/agents/${agent.agent_id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: values.name,
          description: values.description || null,
          is_shared: values.is_shared ?? false,
          default_model: defaultModelFromForm(values.default_model),
          color: nextColor,
          config: nextConfig,
          welcome_message: stored.welcome_message ?? "",
          ...buildAgentRuntimeRequest(values, { clearMissing: true }),
        }),
      });

      if (!skillPackagesSupported) {
        try {
          await skillPackagesApi.replaceMounted(agent.agent_id, []);
        } catch (pkgErr) {
          message.warning(
            apiErrorMessage(pkgErr, t("experts.skillPackagesClearFailed"), t),
          );
        }
      }

      message.success(t("common.saveSuccess"));
      if (bwrapToast?.kind === "success") {
        message.success(bwrapToast.text);
      } else if (bwrapToast?.kind === "warning") {
        message.warning(bwrapToast.text);
      }
      const defaultModel = defaultModelFromForm(values.default_model);
      onSaved({
        agent_id: agent.agent_id,
        name: values.name,
        description: values.description || null,
        default_model: defaultModel,
        is_shared: values.is_shared ?? false,
        color: nextColor,
        icon_url: iconUrl,
      });
      onClose();
    } catch (err) {
      message.error(apiErrorMessage(err, t("experts.patchFailed"), t));
    } finally {
      setSaving(false);
    }
  }, [
    agent.agent_id,
    agent.state,
    agentConfig,
    colorPalette,
    form,
    iconUrl,
    onClose,
    onSaved,
    pathMappings,
    skillPackagesSupported,
    t,
  ]);

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
    modal.confirm({
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
    modal.confirm({
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
    modal.confirm({
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
          <div className={styles.drawerSection} style={{ marginBottom: 0 }}>
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
                name="welcome_message"
                label={t("experts.welcomeMessageTitle")}
                extra={t("experts.editWelcomeHint")}
              >
                <Input.TextArea
                  rows={2}
                  placeholder={t("experts.welcomeMessagePlaceholder")}
                />
              </Form.Item>
              <Form.Item label={t("experts.avatar")}>
                <ExpertAvatarPicker
                  iconUrl={iconUrl}
                  iconName={agent.icon_name}
                  color={
                    isCuratedPalette(colorPalette)
                      ? expertPaletteColor(colorPalette)
                      : colorPalette
                  }
                  disabled={avatarBusy}
                  onPick={(file) => {
                    void (async () => {
                      setAvatarBusy(true);
                      try {
                        const result = await octopAgentsApi.uploadAvatar(
                          agent.agent_id,
                          file,
                        );
                        setIconUrl(result.icon_url);
                        await refresh({ silent: true });
                      } catch (err) {
                        message.error(
                          apiErrorMessage(
                            err,
                            t("experts.avatarUploadFailed"),
                            t,
                          ),
                        );
                        throw err;
                      } finally {
                        setAvatarBusy(false);
                      }
                    })();
                  }}
                  onRemove={() => {
                    void (async () => {
                      setAvatarBusy(true);
                      try {
                        await octopAgentsApi.deleteAvatar(agent.agent_id);
                        setIconUrl(null);
                        await refresh({ silent: true });
                      } catch (err) {
                        message.error(
                          apiErrorMessage(
                            err,
                            t("experts.avatarRemoveFailed"),
                            t,
                          ),
                        );
                      } finally {
                        setAvatarBusy(false);
                      }
                    })();
                  }}
                />
              </Form.Item>
              <Form.Item
                label={t("experts.color")}
                extra={t("experts.colorHint")}
              >
                <ExpertColorPicker
                  value={colorPalette}
                  onChange={setColorPalette}
                />
              </Form.Item>
              <Form.Item
                name="is_shared"
                label={t("experts.share.toggle")}
                valuePropName="checked"
              >
                <Switch />
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
                rootDirMode="edit"
                onAddPathMapping={addPathMapping}
                onRemovePathMapping={removePathMapping}
                onUpdatePathMapping={updatePathMapping}
              />
              {!skillPackagesSupported ? (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginTop: 12 }}
                  message={t("experts.skillPackagesUnsupportedHint")}
                />
              ) : null}
            </Form>

            <Collapse
              ghost
              className={styles.drawerCollapse}
              style={{ margin: "8px 0 0", width: "100%" }}
              defaultActiveKey={["configFiles"]}
              items={[
                {
                  key: "advanced",
                  label: t("experts.advancedOptions"),
                  children: (
                    <Form form={form} layout="vertical" size="middle">
                      <AgentAdvancedConfigFields />
                    </Form>
                  ),
                },
                ...(isAgentChatReady(agent.state)
                  ? [
                      {
                        key: "pageConfig",
                        label: t("experts.pageConfigTitle"),
                        children: (
                          <div style={{ padding: 0 }}>
                            <WelcomeConfig
                              ref={welcomeConfigRef}
                              agentId={agent.agent_id}
                            />
                          </div>
                        ),
                      },
                    ]
                  : []),
              ]}
            />
          </div>

          {isAgentChatReady(agent.state) && (
            <div className={styles.drawerSection} style={{ marginBottom: 0 }}>
              <Collapse
                ghost
                className={styles.drawerCollapse}
                defaultActiveKey={["configFiles"]}
                style={{ margin: 0, width: "100%" }}
                items={[
                  {
                    key: "configFiles",
                    label: (
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          width: "100%",
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
      destroyOnHidden
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
