// dashboard/src/pages/Experts/components/EditAgentDrawer.tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Alert,
  App,
  Button,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Spin,
  Switch,
} from "antd";

import {
  acpApi,
  acpSessionModeText,
  catalogOffersUnattendedMode,
  isUnattendedSessionMode,
  permissionForSessionMode,
} from "../../../api/modules/acp";
import { useAcpSessionModes } from "../../../hooks/useAcpSessionModes";
import { request } from "../../../api/request";
import { AgentAdvancedConfigFields } from "../../../components/AgentAdvancedConfigFields";
import {
  avatarPickerStyles,
  expertPresetSrc,
  isUploadedAvatarUrl,
} from "../../../components/AvatarPicker";
import ExpertColorPicker from "../../../components/ExpertColorPicker";
import AgentTrajectoryField from "./AgentTrajectoryField";
import { workspaceApi } from "../../../api/modules/workspace";
import { skillPackagesApi } from "../../../api/modules/skillPackages";
import { apiErrorMessage, isNotFoundApiError } from "../../../utils/apiError";
import { isAgentChatReady } from "../../../utils/agentError";
import { useAgentFormResources } from "../../../hooks/useAgentFormResources";
import { octopAgentsApi } from "../../../api/modules/octopAgents";
import { useAgent, type OctopAgent } from "../../../context/AgentContext";
import {
  CONVERSATION_MODES,
  parseConversationMode,
  type ConversationMode,
} from "../../Chat/utils/conversationMode";
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
  type AgentCompactionFormValues,
  type AgentRuntimeApiFields,
  type AgentRuntimeFormValues,
} from "../../../utils/agentRuntimeConfig";
import { isBridgeAgentId } from "../../../utils/remoteExpert";
import EditExpertDrawerTitle from "./EditExpertDrawerTitle";
import { useSkillDisplayName } from "../../Agent/Skills/skillDisplayNames";
import { DEFAULT_SKILL_EMOJI } from "../../Agent/Skills/skillMarkdown";
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
  backendSpecForAgentSave,
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
import ManagedRunnerPicker from "./ManagedRunnerPicker";
import RootDirSelect from "./RootDirSelect";
import {
  ResourceVisibilityFormItem,
  useResourceVisibilityAvailable,
} from "../../../components/ResourceVisibilityFields";
import type { ResourceVisibilityMode } from "../../../api/modules/userGroups";
import ExpertComposerDefaultsFields from "./ExpertComposerDefaultsFields";
import SkillCatalogDrawer from "./SkillCatalogDrawer";
import SubagentCatalogDrawer from "./SubagentCatalogDrawer";
import ExpertTextAssistField from "./expertDrawer/ExpertTextAssistField";
import ExpertDrawerSection from "./expertDrawer/ExpertDrawerSection";
import {
  runtimeSettingsFields,
  hasRuntimeSettingsErrors,
} from "./expertDrawer/runtimeSettingsFields";
import ExpertSettingsDrawer from "./expertDrawer/ExpertSettingsDrawer";
import { expertDrawerWidth } from "./expertDrawer/expertDrawerWidth";
import ExpertResourceRow from "./expertDrawer/ExpertResourceRow";
import ExpertFieldLabel from "./expertDrawer/ExpertFieldLabel";
import { SECTION_IDS } from "./expertDrawer/sectionIds";
import expertDrawerStyles from "./expertDrawer/expertDrawer.module.less";
import styles from "../index.module.less";

interface AgentDetail extends AgentRuntimeApiFields {
  id: string;
  name: string;
  description: string | null;
  default_model: string | null;
  color?: string | null;
  icon_url?: string | null;
  compaction?: AgentCompactionFormValues | null;
  welcome_message?: string | null;
  is_shared?: boolean;
  visibility?: ResourceVisibilityMode | null;
  group_ids?: string[];
  knowledge_base_ids?: string[];
  mcp_servers?: string[];
  skill_package_ids?: string[];
  config?: Record<string, unknown>;
}

interface SkillSummary {
  slug?: string;
  name: string;
  description?: string;
  enabled?: boolean;
  kind?: "builtin" | "workspace";
  emoji?: string;
  icon_url?: string;
  corrupt?: boolean;
  error?: string;
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

interface EditFormValues extends AgentRuntimeFormValues {
  name: string;
  description: string;
  welcome_message?: string;
  default_model: string;
  conversation_mode: ConversationMode;
  backend_choice: string;
  composite_default: string;
  root_dir?: string;
  workspace_dir?: string;
  enable_trajectory?: boolean;
  knowledge_base_ids?: string[];
  mcp_servers?: string[];
  skill_package_ids?: string[];
  runner?: string;
  permission_mode?: boolean;
  session_mode?: string;
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
  const [runtimeOpen, setRuntimeOpen] = useState(false);
  const { t, i18n } = useTranslation();
  const { modal, message } = App.useApp();
  const { refresh } = useAgent();
  const skillDisplayName = useSkillDisplayName();
  const [workspaceSettingsOpen, setWorkspaceSettingsOpen] = useState(false);
  const [workspaceDrawerOpen, setWorkspaceDrawerOpen] = useState(false);
  const [form] = Form.useForm<EditFormValues>();
  const watchedRunner = Form.useWatch("runner", form);
  const sessionModes = useAcpSessionModes(
    agent.kind === "managed" ? watchedRunner : "",
  );

  useEffect(() => {
    if (agent.kind !== "managed" || sessionModes.length === 0) return;
    const current = String(form.getFieldValue("session_mode") ?? "");
    if (sessionModes.some((mode) => mode.id === current)) return;
    const yolo = form.getFieldValue("permission_mode") === true;
    const preferred = yolo
      ? sessionModes.find((mode) => isUnattendedSessionMode(mode.id))
      : undefined;
    form.setFieldValue("session_mode", (preferred ?? sessionModes[0]).id);
  }, [agent.kind, form, sessionModes]);
  const [workspaceFiles, setWorkspaceFiles] = useState<string[]>([]);
  const [agentSkills, setAgentSkills] = useState<SkillSummary[]>([]);
  const [agentSubagents, setAgentSubagents] = useState<SubagentSummary[]>([]);
  const remote = Boolean(agent.bridge) || isBridgeAgentId(agent.agent_id);
  const { models, modelsLoading, backends, backendsLoading } =
    useAgentFormResources(true, agent.agent_id);
  const [pathMappings, setPathMappings] = useState<PathMapping[]>([]);
  const [agentConfig, setAgentConfig] = useState<Record<string, unknown>>({});
  const [runners, setRunners] = useState<string[]>([]);
  const [runnersReady, setRunnersReady] = useState(false);
  const [skillPackages, setSkillPackages] = useState<
    { id: string; name: string }[]
  >([]);
  const [skillPackagesLoading, setSkillPackagesLoading] = useState(false);
  const [colorPalette, setColorPalette] = useState<string>(
    () => parseStoredColor(agent.color) ?? DEFAULT_PALETTE,
  );
  const [iconUrl, setIconUrl] = useState<string | null>(agent.icon_url);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [filesLoading, setFilesLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [expertVisibility, setExpertVisibility] =
    useState<ResourceVisibilityMode>(agent.is_shared ? "all" : "owner");
  const [expertGroupIds, setExpertGroupIds] = useState<string[]>([]);
  const sharingAvailable = useResourceVisibilityAvailable({
    allowOwner: true,
    visibility: expertVisibility,
  });
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
  const [skillCatalogOpen, setSkillCatalogOpen] = useState(false);
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
  const runnerChoices = useMemo(() => {
    const current =
      typeof agentConfig.managed_runner === "string"
        ? agentConfig.managed_runner.trim()
        : "";
    if (current && !runners.includes(current)) return [current, ...runners];
    return runners;
  }, [agentConfig.managed_runner, runners]);

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
          default_model: defaultModelToForm(ag.default_model),
          conversation_mode: parseConversationMode(cfg.conversation_mode),
          backend_choice: parsedBackend.backendChoice,
          composite_default: parsedBackend.compositeDefault,
          root_dir: parsedBackend.rootDir,
          workspace_dir:
            typeof cfg.workspace_dir === "string" ? cfg.workspace_dir : "",
          ...readAgentRuntimeFormValues(ag),
          enable_trajectory: cfg.enable_trajectory !== false,
          runner:
            typeof cfg.managed_runner === "string" ? cfg.managed_runner : "",
          permission_mode: cfg.managed_permission_mode === "yolo",
          session_mode:
            typeof cfg.managed_session_mode === "string" &&
            cfg.managed_session_mode.trim()
              ? cfg.managed_session_mode.trim()
              : String(form.getFieldValue("session_mode") ?? ""),
          knowledge_base_ids: Array.isArray(ag.knowledge_base_ids)
            ? ag.knowledge_base_ids
            : [],
          mcp_servers: Array.isArray(ag.mcp_servers) ? ag.mcp_servers : [],
          skill_package_ids: Array.isArray(ag.skill_package_ids)
            ? ag.skill_package_ids
            : [],
        });
        const nextVisibility: ResourceVisibilityMode =
          ag.visibility === "groups" ||
          ag.visibility === "all" ||
          ag.visibility === "owner"
            ? ag.visibility
            : ag.is_shared
            ? "all"
            : "owner";
        setExpertVisibility(nextVisibility);
        setExpertGroupIds(
          nextVisibility === "groups" ? ag.group_ids ?? [] : [],
        );
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
              if (cancelled) return;
              const list = skills || [];
              const corrupt = list.filter((skill) => skill.corrupt);
              if (corrupt.length > 0) {
                message.warning(
                  t("skills.corruptSkipped", {
                    slugs: corrupt
                      .map((skill) => skill.slug ?? skill.name)
                      .join(", "),
                  }),
                );
              }
              setAgentSkills(
                workspaceSkills(list.filter((skill) => !skill.corrupt)),
              );
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
  }, [agent.agent_id, agent.state, form, message, t]);

  useEffect(() => {
    if (agent.kind !== "managed") return;
    let cancelled = false;
    setRunnersReady(false);
    acpApi
      .getGlobalRunners()
      .then((data) => {
        if (cancelled) return;
        setRunners(
          Object.entries(data.runners)
            .filter(([, spec]) => spec.enabled)
            .map(([name]) => name),
        );
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setRunners([]);
          message.error(
            apiErrorMessage(err, t("experts.managed.loadFailed"), t),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setRunnersReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [agent.agent_id, agent.kind, message, t]);

  useEffect(() => {
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
  }, [agent.agent_id]);

  const handleSave = useCallback(async () => {
    const values = await form.validateFields().catch(() => {
      if (hasRuntimeSettingsErrors(form)) setRuntimeOpen(true);
      return undefined;
    });
    if (!values) return;
    if (values.backend_choice === "composite") {
      const pathError = validatePathMappings(pathMappings, t);
      if (pathError) {
        message.error(pathError);
        return;
      }
    }
    if (!remote && shouldProbeRootDir(values.backend_choice, values.root_dir)) {
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
      if (
        !remote &&
        shouldProbeRootDir(values.backend_choice, values.root_dir)
      ) {
        const bwrap = await ensureBubblewrapAfterProbe();
        const kind = ensureBwrapToastKind(bwrap.status);
        if (kind !== "none") {
          bwrapToast = { kind, text: ensureBwrapMessage(bwrap, t) };
        }
      }

      const backendSpec = backendSpecForAgentSave(
        agent.kind,
        agentConfig.backend,
        values.backend_choice,
        values.composite_default ?? DEFAULT_BACKEND,
        pathMappings,
        values.root_dir,
      );

      const nextColor = isCuratedPalette(colorPalette)
        ? expertPaletteColor(colorPalette)
        : colorPalette;
      const configPatch: Record<string, unknown> =
        agent.kind === "managed"
          ? {}
          : { conversation_mode: values.conversation_mode };
      const managedRunner = values.runner?.trim();
      if (agent.kind === "managed" && managedRunner) {
        configPatch.managed_runner = managedRunner;
        const sessionMode = values.session_mode?.trim() ?? "";
        configPatch.managed_session_mode = sessionMode;
        configPatch.managed_permission_mode = permissionForSessionMode(
          sessionModes,
          sessionMode,
          values.permission_mode === true,
        );
      }
      const nextConfig = omitAgentRuntimeConfig({
        ...agentConfig,
        backend: backendSpec,
        enable_trajectory: values.enable_trajectory === true,
        ...configPatch,
      });
      if (agent.kind === "managed") {
        delete nextConfig.conversation_mode;
      }
      delete nextConfig.color;
      delete nextConfig.icon_name;
      delete nextConfig.icon_url;
      delete nextConfig.expert_id;
      delete nextConfig.skill_package_ids;
      delete nextConfig.published_expert_id;
      delete nextConfig.welcome_message;
      delete nextConfig.knowledge_base_ids;
      delete nextConfig.mcp_servers;

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
          is_shared: expertVisibility !== "owner",
          visibility: expertVisibility,
          group_ids: expertVisibility === "groups" ? expertGroupIds : [],
          ...(agent.kind === "managed"
            ? {
                knowledge_base_ids: stored.knowledge_base_ids ?? [],
                mcp_servers: stored.mcp_servers ?? [],
                skill_package_ids: stored.skill_package_ids ?? [],
              }
            : {
                default_model: defaultModelFromForm(values.default_model),
                knowledge_base_ids: stored.knowledge_base_ids ?? [],
                mcp_servers: stored.mcp_servers ?? [],
                ...(skillPackagesSupported
                  ? { skill_package_ids: stored.skill_package_ids ?? [] }
                  : {}),
                ...buildAgentRuntimeRequest(values, { clearMissing: true }),
              }),
          color: nextColor,
          config: nextConfig,
          welcome_message: stored.welcome_message ?? "",
        }),
      });

      if (!remote && agent.kind !== "managed" && !skillPackagesSupported) {
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
        is_shared: expertVisibility !== "owner",
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
    agent.kind,
    agent.state,
    agentConfig,
    remote,
    colorPalette,
    expertGroupIds,
    expertVisibility,
    form,
    iconUrl,
    onClose,
    onSaved,
    pathMappings,
    sessionModes,
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

  const chatReady = isAgentChatReady(agent.state);
  const expertVisibilityField = sharingAvailable ? (
    <ResourceVisibilityFormItem
      allowOwner
      visibility={expertVisibility}
      groupIds={expertGroupIds}
      tooltip={t("experts.visibilityHint")}
      onChange={(next) => {
        setExpertVisibility(next.visibility);
        setExpertGroupIds(next.visibility === "groups" ? next.groupIds : []);
      }}
    />
  ) : null;

  return (
    <>
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 40 }}>
          <Spin />
        </div>
      ) : (
        <>
          {remote ? (
            <Alert
              type="info"
              showIcon
              message={t("chat.remoteExpert.editBanner")}
              style={{ marginBottom: 16 }}
            />
          ) : null}
          <Form
            form={form}
            layout="vertical"
            size="middle"
            className={expertDrawerStyles.formArea}
          >
            {/* ── Identity ─────────────────────────────────────── */}
            <ExpertDrawerSection id={SECTION_IDS.identity}>
              <Form.Item
                label={t("experts.avatar")}
                tooltip={t("experts.avatarHint")}
                className={avatarPickerStyles.formItem}
              >
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
                  onSelectPreset={(presetId) => {
                    void (async () => {
                      setAvatarBusy(true);
                      try {
                        if (isUploadedAvatarUrl(iconUrl)) {
                          await octopAgentsApi.deleteAvatar(agent.agent_id);
                        }
                        const nextUrl = expertPresetSrc(presetId ?? "default");
                        await request(`/agents/${agent.agent_id}`, {
                          method: "PATCH",
                          body: JSON.stringify({ icon_url: nextUrl }),
                        });
                        setIconUrl(nextUrl);
                        await refresh({ silent: true });
                      } catch (err) {
                        message.error(
                          apiErrorMessage(
                            err,
                            t("experts.avatarUploadFailed"),
                            t,
                          ),
                        );
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
                tooltip={t("experts.colorHint")}
              >
                <ExpertColorPicker
                  value={colorPalette}
                  onChange={setColorPalette}
                />
              </Form.Item>
              <Form.Item
                name="name"
                label={t("experts.agentName")}
                rules={[
                  { required: true, message: t("experts.pleaseEnterName") },
                ]}
              >
                <Input />
              </Form.Item>
              <ExpertTextAssistField
                name="description"
                label={t("experts.agentDescription")}
                kind="expert.description"
              >
                <Input.TextArea autoSize={{ minRows: 2 }} />
              </ExpertTextAssistField>
              {agent.kind === "managed" ? null : (
                <>
                  <Form.Item
                    name="conversation_mode"
                    label={t("experts.defaultModeLabel")}
                    tooltip={t("experts.defaultModeHint")}
                  >
                    <Select
                      options={CONVERSATION_MODES.map((mode) => ({
                        value: mode,
                        label: t(`chat.conversationMode.${mode}`),
                      }))}
                    />
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
                </>
              )}
              {expertVisibilityField}
            </ExpertDrawerSection>

            {/* ── Skills & resources ───────────────────────────── */}
            <ExpertDrawerSection id={SECTION_IDS.resources}>
              {agent.kind === "managed" ? (
                <>
                  <Form.Item
                    name="skill_package_ids"
                    label={t("experts.skillPackagesLabel")}
                    tooltip={t("experts.managedSkillPackagesHint")}
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
                </>
              ) : (
                <>
                  <ExpertComposerDefaultsFields agentId={agent.agent_id} />
                  <Form.Item
                    name="skill_package_ids"
                    label={t("experts.skillPackagesLabel")}
                    tooltip={
                      skillPackagesSupported
                        ? t("experts.skillPackagesHint")
                        : t("experts.skillPackagesUnsupportedHint")
                    }
                  >
                    <Select
                      mode="multiple"
                      allowClear
                      disabled={!skillPackagesSupported}
                      loading={skillPackagesLoading}
                      options={skillPackages.map((pack) => ({
                        value: pack.id,
                        label: pack.name,
                      }))}
                      placeholder={t("experts.skillPackagesPlaceholder")}
                    />
                  </Form.Item>
                </>
              )}
            </ExpertDrawerSection>

            {agent.kind === "managed" ? (
              <ExpertDrawerSection id={SECTION_IDS.workspace}>
                {runnersReady && runnerChoices.length === 0 ? (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message={t("experts.managed.noRunners")}
                  />
                ) : null}
                <Form.Item
                  name="runner"
                  colon={false}
                  className={styles.runnerField}
                  label={
                    <span className={styles.runnerFieldLabel}>
                      <span>{t("experts.managed.runner")}</span>
                      <Link to="/acp" className={styles.runnerManageLink}>
                        {t("experts.managed.manageAcp")}
                      </Link>
                    </span>
                  }
                  rules={[
                    {
                      required: true,
                      message: t("experts.managed.runnerRequired"),
                    },
                  ]}
                >
                  <ManagedRunnerPicker runners={runnerChoices} />
                </Form.Item>
                {sessionModes.length > 0 ? (
                  <Form.Item
                    name="session_mode"
                    label={t("chat.conversationMode.picker")}
                    tooltip={t("experts.managed.sessionModeHint")}
                  >
                    <Select
                      options={sessionModes.map((mode) => ({
                        value: mode.id,
                        label: acpSessionModeText(mode, i18n.language, "name"),
                        title: acpSessionModeText(mode, i18n.language, "hint"),
                      }))}
                    />
                  </Form.Item>
                ) : null}
                {catalogOffersUnattendedMode(sessionModes) ? null : (
                  <Form.Item
                    name="permission_mode"
                    label={t("experts.managed.yolo")}
                    valuePropName="checked"
                    tooltip={t("experts.managed.yoloHint")}
                  >
                    <Switch size="small" />
                  </Form.Item>
                )}
              </ExpertDrawerSection>
            ) : null}

            <ExpertDrawerSection id={SECTION_IDS.advanced} compact>
              <Form.Item name="welcome_message" noStyle>
                <WelcomeConfig
                  key={agent.agent_id}
                  ref={welcomeConfigRef}
                  agentId={chatReady ? agent.agent_id : undefined}
                  showPrompts={chatReady}
                  editing
                  disabled={saving}
                />
              </Form.Item>
              <ExpertSettingsDrawer
                title={t("experts.expertFilesAccessTitle")}
                summary={t(
                  agent.kind === "managed"
                    ? "experts.managedWorkspaceAccessSummary"
                    : "experts.workspaceAccessSummary",
                )}
                open={workspaceSettingsOpen}
                onOpenChange={setWorkspaceSettingsOpen}
              >
                {chatReady && agent.kind !== "managed" ? (
                  <Form.Item
                    label={
                      <ExpertFieldLabel
                        label={t("experts.mdFilesTitle")}
                        tooltip={t("experts.promptFilesHint")}
                        action={t("experts.openWorkspace")}
                        onAction={() => {
                          setWorkspaceSettingsOpen(false);
                          setWorkspaceDrawerOpen(true);
                        }}
                      />
                    }
                  >
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
                      <div className={expertDrawerStyles.rowEmpty}>
                        {t("experts.noWorkspaceFiles")}
                      </div>
                    ) : (
                      <div className={expertDrawerStyles.rowList}>
                        {workspaceFiles.map((file) => {
                          const basename = displayName(file);
                          const meta = metaForFile(basename, t);
                          return (
                            <ExpertResourceRow
                              key={file}
                              icon={meta.icon}
                              iconStyle={{
                                color: meta.color,
                                background: `${meta.color}1a`,
                              }}
                              label={meta.label}
                              secondary={basename}
                              hint={t("experts.editFile")}
                              onOpen={() => openFileEditor(file)}
                              menuItems={[
                                {
                                  key: "rename",
                                  label: t("workspace.rename"),
                                  onClick: () => openListRename(file, "config"),
                                },
                                {
                                  key: "delete",
                                  label: t("common.delete"),
                                  danger: true,
                                  onClick: () => confirmDeleteConfigFile(file),
                                },
                              ]}
                              menuLabel={t("common.more")}
                            />
                          );
                        })}
                      </div>
                    )}
                  </Form.Item>
                ) : null}
                {chatReady && agent.kind !== "managed" ? (
                  <>
                    <Form.Item
                      label={
                        <ExpertFieldLabel
                          label={t("experts.skillFilesTitle", {
                            count: agentSkills.length,
                          })}
                          action={t("experts.manageSkills")}
                          onAction={() => setSkillCatalogOpen(true)}
                        />
                      }
                    >
                      {agentSkills.length === 0 ? (
                        <div className={expertDrawerStyles.rowEmpty}>
                          {t("experts.noSkillFiles")}
                        </div>
                      ) : (
                        <div className={expertDrawerStyles.rowList}>
                          {agentSkills.map((skill) => {
                            const iconUrl = skill.icon_url?.trim();
                            const label = skillDisplayName(skill);
                            return (
                              <ExpertResourceRow
                                key={skill.slug ?? skill.name}
                                icon={
                                  iconUrl ? (
                                    <img
                                      src={iconUrl}
                                      alt={label}
                                      className={expertDrawerStyles.rowIconImg}
                                    />
                                  ) : (
                                    skill.emoji?.trim() || DEFAULT_SKILL_EMOJI
                                  )
                                }
                                iconStyle={{
                                  color: "#8B5CF6",
                                  background: iconUrl
                                    ? "transparent"
                                    : "#8B5CF61a",
                                }}
                                label={label}
                                secondary={skill.description || "SKILL.md"}
                                secondaryIsPath={false}
                                hint={t("experts.editFile")}
                                onOpen={() =>
                                  openFileEditor(
                                    `/skills/${
                                      skill.slug ?? skill.name
                                    }/SKILL.md`,
                                  )
                                }
                                menuItems={[
                                  {
                                    key: "delete",
                                    label: t("common.delete"),
                                    danger: true,
                                    onClick: () => confirmDeleteSkill(skill),
                                  },
                                ]}
                                menuLabel={t("common.more")}
                              />
                            );
                          })}
                        </div>
                      )}
                    </Form.Item>
                    <Form.Item
                      label={
                        <ExpertFieldLabel
                          label={t("experts.subagentFilesTitle", {
                            count: agentSubagents.length,
                          })}
                          action={t("experts.manageSubagents")}
                          onAction={() => setSubagentCatalogOpen(true)}
                        />
                      }
                    >
                      {agentSubagents.length === 0 ? (
                        <div className={expertDrawerStyles.rowEmpty}>
                          {t("experts.noSubagentFiles")}
                        </div>
                      ) : (
                        <div className={expertDrawerStyles.rowList}>
                          {agentSubagents.map((subagent) => (
                            <ExpertResourceRow
                              key={subagent.slug}
                              icon={subagent.emoji ?? "🤖"}
                              iconStyle={{
                                color: "#6366f1",
                                background: "#6366f11a",
                              }}
                              label={subagent.name}
                              secondary={
                                subagent.description ||
                                subagent.path.replace(/^\//, "")
                              }
                              secondaryIsPath={!subagent.description}
                              hint={t("experts.editFile")}
                              onOpen={() =>
                                openFileEditor(subagentFilePath(subagent.path))
                              }
                              menuItems={[
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
                              ]}
                              menuLabel={t("common.more")}
                            />
                          ))}
                        </div>
                      )}
                    </Form.Item>
                  </>
                ) : null}
                <AgentTrajectoryField />
                {agent.kind === "managed" ? (
                  <Form.Item
                    name="workspace_dir"
                    label={t("experts.workspaceDir")}
                    tooltip={t("experts.workspaceDirImmutableHint")}
                  >
                    <RootDirSelect disabled />
                  </Form.Item>
                ) : (
                  <AgentBackendFields
                    backends={backends}
                    backendsLoading={backendsLoading}
                    backendChoice={backendChoice}
                    pathMappings={pathMappings}
                    rootDirMode="edit"
                    disabled
                    skipHostFilesystem={remote}
                    onAddPathMapping={addPathMapping}
                    onRemovePathMapping={removePathMapping}
                    onUpdatePathMapping={updatePathMapping}
                  />
                )}
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
                <SkillCatalogDrawer
                  agentId={agent.agent_id}
                  open={skillCatalogOpen}
                  onClose={() => {
                    setSkillCatalogOpen(false);
                    void reloadSkills();
                  }}
                />
                <FileEditModal
                  open={fileModalOpen}
                  agentId={agent.agent_id}
                  filePath={editingFile}
                  onClose={() => setFileModalOpen(false)}
                  onSaved={() => {
                    /* file saved */
                  }}
                />
              </ExpertSettingsDrawer>
              {agent.kind === "managed" ? null : (
                <ExpertSettingsDrawer
                  title={t("experts.advancedOptions")}
                  summary={t("experts.runtimeSettingsSummary")}
                  fields={runtimeSettingsFields}
                  open={runtimeOpen}
                  onOpenChange={setRuntimeOpen}
                >
                  <AgentAdvancedConfigFields grouped />
                </ExpertSettingsDrawer>
              )}
            </ExpertDrawerSection>
          </Form>
        </>
      )}
      <WorkspaceDrawer
        agentId={agent.agent_id}
        open={workspaceDrawerOpen}
        onClose={() => setWorkspaceDrawerOpen(false)}
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
      title={<EditExpertDrawerTitle agent={agent} />}
      width={expertDrawerWidth}
      onClose={onClose}
      destroyOnHidden
      className={`${styles.expertDrawer} ${expertDrawerStyles.expertDrawer}`}
      rootClassName={styles.expertDrawerRoot}
      footer={
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            type="primary"
            loading={saving}
            onClick={() => void saveRef.current?.()}
          >
            {saving ? t("experts.savingInProgress") : t("common.save")}
          </Button>
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
