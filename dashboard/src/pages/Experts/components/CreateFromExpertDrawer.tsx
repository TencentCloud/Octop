// dashboard/src/pages/Experts/components/CreateFromExpertDrawer.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, Button, Drawer, Form, Input, Select, Spin } from "antd";
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
import {
  avatarPickerStyles,
  expertPresetSrc,
} from "../../../components/AvatarPicker";
import ExpertColorPicker from "../../../components/ExpertColorPicker";
import AgentTrajectoryField from "./AgentTrajectoryField";
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
  emptyAgentRuntimeFormValues,
  type AgentRuntimeFormValues,
} from "../../../utils/agentRuntimeConfig";
import { useAgentFormResources } from "../../../hooks/useAgentFormResources";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { pickLocale } from "../../../utils/localizedText";
import {
  buildModelSelectOptions,
  defaultModelFromForm,
  MODEL_AUTO_VALUE,
} from "../../../utils/modelOptions";
import {
  CONVERSATION_MODES,
  DEFAULT_CONVERSATION_MODE,
  type ConversationMode,
} from "../../Chat/utils/conversationMode";
import type { ExpertSummary } from "./ExpertCard";
import {
  filterConfigMdFiles,
  groupExpertFiles,
  type NamedFileContent,
} from "./expertFileGroups";
import { metaForFile } from "./iconForName";
import {
  buildBackendSpec,
  DEFAULT_BACKEND,
  defaultCreateBackendChoice,
  ensureBubblewrapAfterProbe,
  ensureBwrapMessage,
  ensureBwrapToastKind,
  probeRootDir,
  rootDirProbeMessage,
  createWorkspaceSelection,
  shouldProbeRootDir,
  shouldProbeWorkspaceDir,
  supportsHostSkillPackages,
  validatePathMappings,
  type PathMapping,
} from "./agentBackendForm";
import AgentBackendFields from "./AgentBackendFields";
import ExpertAvatarPicker from "./ExpertAvatarPicker";
import {
  ResourceVisibilityFormItem,
  useResourceVisibilityAvailable,
} from "../../../components/ResourceVisibilityFields";
import type { ResourceVisibilityMode } from "../../../api/modules/userGroups";
import ExpertComposerDefaultsFields from "./ExpertComposerDefaultsFields";
import WelcomeConfig, { type WelcomeConfigRef } from "./WelcomeConfig";
import {
  normalizeQuickPrompts,
  serializeQuickPrompts,
  shouldWriteWelcomeManifest,
  type QuickPrompt,
} from "./welcomeManifest";
import FileEditModal from "./FileEditModal";
import SkillSourcePickerModal, {
  type PickedAgentSkill,
  type PickedHubSkill,
} from "./SkillSourcePickerModal";
import SubagentSourcePickerModal, {
  type PickedCatalogSubagent,
} from "./SubagentSourcePickerModal";
import {
  diffComposerFiles,
  ensurePromptFiles,
  removeComposerSkill,
  removeComposerSubagent,
  upsertComposerFile,
} from "./composerFiles";
import ExpertTextAssistField from "./expertDrawer/ExpertTextAssistField";
import ExpertDrawerSection from "./expertDrawer/ExpertDrawerSection";
import {
  runtimeSettingsFields,
  hasRuntimeSettingsErrors,
} from "./expertDrawer/runtimeSettingsFields";
import ExpertSettingsDrawer from "./expertDrawer/ExpertSettingsDrawer";
import { expertDrawerWidth } from "./expertDrawer/expertDrawerWidth";
import ExpertResourceRow from "./expertDrawer/ExpertResourceRow";
import ExpertFilePreviewList from "./expertDrawer/ExpertFilePreviewList";
import ExpertFieldLabel from "./expertDrawer/ExpertFieldLabel";
import { SECTION_IDS } from "./expertDrawer/sectionIds";
import expertDrawerStyles from "./expertDrawer/expertDrawer.module.less";
import styles from "../index.module.less";

type FileContent = NamedFileContent;

interface ExpertDetail {
  file_contents?: FileContent[];
  welcome_message?: { zh?: string; en?: string };
  quick_prompts?: QuickPrompt[];
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

function warnComposerPartial(
  body: { hub_skill_errors?: string[]; copy_skill_errors?: string[] },
  t: (key: string, opts?: Record<string, string>) => string,
) {
  if (body.hub_skill_errors?.length) {
    message.warning(
      t("experts.hubSkillsPartial", {
        names: body.hub_skill_errors.join(", "),
      }),
    );
  }
  if (body.copy_skill_errors?.length) {
    message.warning(
      t("experts.copySkillsPartial", {
        names: body.copy_skill_errors.join(", "),
      }),
    );
  }
}

function sourceQuickPrompts(source: CreateFromTemplateSource): QuickPrompt[] {
  return normalizeQuickPrompts(source.expert.quick_prompts);
}

function sourceIcon(source: CreateFromTemplateSource | null): {
  iconUrl: string | null;
  iconName: string | null;
} {
  if (!source) return { iconUrl: null, iconName: null };
  if (source.kind === "builtin") {
    return {
      iconUrl: source.expert.icon_url ?? null,
      iconName: source.expert.icon_name ?? null,
    };
  }
  if (source.kind === "published") {
    return {
      iconUrl: source.expert.icon_url ?? null,
      iconName: source.expert.icon_name,
    };
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
  const [runtimeOpen, setRuntimeOpen] = useState(false);
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  const allowedBackendTypes = currentUser?.allowed_backend_types;
  const createBackendChoice = defaultCreateBackendChoice(
    allowedBackendTypes,
    currentUser?.default_backend_type,
  );
  const [form] = Form.useForm<
    {
      name: string;
      description: string;
      agent_id?: string;
      welcome_message?: string;
      default_model: string;
      conversation_mode: ConversationMode;
      backend_choice: string;
      composite_default: string;
      root_dir?: string;
      workspace_dir?: string;
      workspace_dir_auto?: string;
      skill_package_ids?: string[];
      knowledge_base_ids?: string[];
      mcp_servers?: string[];
      enable_trajectory?: boolean;
    } & AgentRuntimeFormValues
  >();
  const [submitting, setSubmitting] = useState(false);

  const { models, modelsLoading, backends, backendsLoading } =
    useAgentFormResources(open && !!source);

  const [pathMappings, setPathMappings] = useState<PathMapping[]>([]);

  const [fileContents, setFileContents] = useState<FileContent[]>([]);
  const [originalFileContents, setOriginalFileContents] = useState<
    FileContent[]
  >([]);
  const [pendingHubSkills, setPendingHubSkills] = useState<PickedHubSkill[]>(
    [],
  );
  const [pendingCopySkills, setPendingCopySkills] = useState<
    { agent_id: string; slug: string }[]
  >([]);
  const [skillPickerOpen, setSkillPickerOpen] = useState(false);
  const [subagentPickerOpen, setSubagentPickerOpen] = useState(false);
  const [localEditPath, setLocalEditPath] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [skillPackages, setSkillPackages] = useState<SkillPackage[]>([]);
  const [skillPackagesLoading, setSkillPackagesLoading] = useState(false);
  const [colorPalette, setColorPalette] = useState<string>("rose");
  const [expertVisibility, setExpertVisibility] =
    useState<ResourceVisibilityMode>("owner");

  const sharingAvailable = useResourceVisibilityAvailable({
    allowOwner: true,
    visibility: expertVisibility,
  });
  const [expertGroupIds, setExpertGroupIds] = useState<string[]>([]);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [avatarPresetId, setAvatarPresetId] = useState<string | null>(null);
  const [avatarPresetTouched, setAvatarPresetTouched] = useState(false);
  const [detailPrompts, setDetailPrompts] = useState<QuickPrompt[] | null>(
    null,
  );
  const [promptsSourceKey, setPromptsSourceKey] = useState("");
  const welcomeConfigRef = useRef<WelcomeConfigRef>(null);

  const backendChoice =
    Form.useWatch("backend_choice", form) ?? DEFAULT_BACKEND;
  const watchedRootDir = Form.useWatch("root_dir", form);
  const skillPackagesSupported = supportsHostSkillPackages({
    backendChoice,
    rootDir: watchedRootDir,
  });

  useEffect(() => {
    if (skillPackagesSupported) return;
    form.setFieldsValue({ skill_package_ids: [] });
  }, [skillPackagesSupported, form]);

  const sourceKey = useMemo(() => {
    if (!source) return "";
    if (source.kind === "builtin") return `builtin:${source.expert.id}`;
    if (source.kind === "published") return `published:${source.expert.id}`;
    return `market:${source.expert.slug}`;
  }, [source]);
  const listPrompts = useMemo(
    () => (source ? sourceQuickPrompts(source) : []),
    [source],
  );
  if (promptsSourceKey !== sourceKey) {
    setPromptsSourceKey(sourceKey);
    setDetailPrompts(null);
  }
  const templatePrompts = detailPrompts ?? listPrompts;

  useEffect(() => {
    if (!open || !source) return;
    let cancelled = false;

    setPathMappings([]);
    setExpertVisibility("owner");
    setExpertGroupIds([]);
    const defaults = sourceDefaults(source, lang);
    setColorPalette(parseStoredColor(defaults.color) ?? DEFAULT_PALETTE);
    setAvatarFile(null);
    setAvatarPresetId(null);
    setAvatarPresetTouched(false);
    setAvatarPreview((prev) => {
      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
      return null;
    });
    form.setFieldsValue({
      name: defaults.name,
      description: defaults.description,
      agent_id: undefined,
      welcome_message: defaults.welcome_message,
      default_model: MODEL_AUTO_VALUE,
      conversation_mode: DEFAULT_CONVERSATION_MODE,
      backend_choice: createBackendChoice,
      composite_default: DEFAULT_BACKEND,
      workspace_dir: "",
      workspace_dir_auto: "",
      skill_package_ids: [],
      knowledge_base_ids: [],
      mcp_servers: [],
      enable_trajectory: true,
      ...emptyAgentRuntimeFormValues(),
    });

    setPendingHubSkills([]);
    setPendingCopySkills([]);
    setLocalEditPath(null);
    setSubagentPickerOpen(false);
    setDetailPrompts(null);
    setFileContents([]);
    setOriginalFileContents([]);
    setDetailLoading(true);
    const templateDetail =
      source.kind === "market"
        ? Promise.resolve<ExpertDetail>({})
        : request<ExpertDetail>(
            source.kind === "builtin"
              ? `/experts/${encodeURIComponent(source.expert.id)}`
              : `/experts/published/${encodeURIComponent(source.expert.id)}`,
          );

    void Promise.allSettled([
      request<FileContent[]>("/experts/default-prompt-files"),
      templateDetail,
    ]).then(([defaults, detail]) => {
      if (cancelled) return;
      const data = detail.status === "fulfilled" ? detail.value : {};
      const files = new Map(
        (defaults.status === "fulfilled" ? defaults.value : []).map((file) => [
          file.name,
          file,
        ]),
      );
      for (const file of data.file_contents ?? []) files.set(file.name, file);
      const initialFiles = ensurePromptFiles([...files.values()]);
      setFileContents(initialFiles);
      setOriginalFileContents(initialFiles);
      if (data.quick_prompts)
        setDetailPrompts(normalizeQuickPrompts(data.quick_prompts));
      const welcomeText = pickLocale(data.welcome_message, lang);
      if (welcomeText) form.setFieldsValue({ welcome_message: welcomeText });
      if (detail.status === "rejected") {
        message.warning(t("experts.loadDetailFailed"));
      }
      setDetailLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [open, source, sourceKey, lang, form, createBackendChoice, t]);

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
    const values = await form.validateFields().catch(() => {
      if (hasRuntimeSettingsErrors(form)) setRuntimeOpen(true);
      return undefined;
    });
    if (!values) return;
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
    const autoWorkspaceDir = form.getFieldValue("workspace_dir_auto");
    const workspaceSelection = createWorkspaceSelection({
      backendChoice: values.backend_choice,
      rootDir: values.root_dir,
      workspaceDir: values.workspace_dir,
      autoWorkspaceDir,
      agentId: values.agent_id,
    });
    const workspaceDir = workspaceSelection.workspaceDir;
    if (
      workspaceDir &&
      shouldProbeWorkspaceDir(
        values.backend_choice,
        workspaceDir,
        autoWorkspaceDir,
      )
    ) {
      const probe = await probeRootDir(workspaceDir);
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
      const composerPatch = diffComposerFiles(
        originalFileContents,
        fileContents,
      );
      const welcomeSnap = welcomeConfigRef.current?.getSnapshot();
      const pageConfigPrompts =
        welcomeSnap &&
        shouldWriteWelcomeManifest(welcomeSnap.status, welcomeSnap.dirty)
          ? serializeQuickPrompts(welcomeSnap.data.quick_prompts)
          : undefined;
      const payload = {
        name: values.name,
        description: values.description || undefined,
        agent_id: workspaceSelection.agentId,
        default_model: defaultModelFromForm(values.default_model) ?? undefined,
        backend: backendSpec,
        ...(workspaceDir ? { workspace_dir: workspaceDir } : {}),
        skill_package_ids: skillPackagesSupported
          ? values.skill_package_ids ?? []
          : [],
        knowledge_base_ids: values.knowledge_base_ids ?? [],
        mcp_servers: values.mcp_servers ?? [],
        color: isCuratedPalette(colorPalette)
          ? expertPaletteColor(colorPalette)
          : colorPalette,
        ...(welcomeText ? { welcome_message: welcomeText } : {}),
        ...buildAgentRuntimeRequest(values),
        enable_trajectory: values.enable_trajectory === true,
        conversation_mode: values.conversation_mode,
        visibility: expertVisibility,
        group_ids: expertVisibility === "groups" ? expertGroupIds : [],
        ...(composerPatch.file_overrides.length
          ? { file_overrides: composerPatch.file_overrides }
          : {}),
        ...(composerPatch.omit_files.length
          ? { omit_files: composerPatch.omit_files }
          : {}),
        ...(pendingHubSkills.length ? { hub_skills: pendingHubSkills } : {}),
        ...(pendingCopySkills.length ? { copy_skills: pendingCopySkills } : {}),
        ...(pageConfigPrompts !== undefined
          ? { quick_prompts: pageConfigPrompts }
          : {}),
      };

      let body: {
        agent_id: string;
        name: string;
        hub_skill_errors?: string[];
        copy_skill_errors?: string[];
      };
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
        body = {
          agent_id: created.agent_id,
          name: created.name,
          hub_skill_errors: created.hub_skill_errors,
          copy_skill_errors: created.copy_skill_errors,
        };
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
      warnComposerPartial(body, t);
      if (avatarFile) {
        try {
          await octopAgentsApi.uploadAvatar(body.agent_id, avatarFile);
        } catch {
          message.warning(t("experts.avatarUploadLater"));
        }
      } else if (avatarPresetTouched) {
        try {
          await request(`/agents/${body.agent_id}`, {
            method: "PATCH",
            body: JSON.stringify({
              icon_url: expertPresetSrc(avatarPresetId ?? "default"),
            }),
          });
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

  const { configFiles, skillGroups, subagentFiles } = groupExpertFiles(
    ensurePromptFiles(fileContents),
  );
  const selectedSkillSlugs = useMemo(() => {
    const slugs = new Set(skillGroups.map((group) => group.name));
    for (const skill of pendingHubSkills) slugs.add(skill.skill_name);
    for (const skill of pendingCopySkills) slugs.add(skill.slug);
    return slugs;
  }, [pendingCopySkills, pendingHubSkills, skillGroups]);

  const localEditFile = localEditPath
    ? fileContents.find((file) => file.name === localEditPath) ?? null
    : null;

  const handlePickHubSkill = (skill: PickedHubSkill) => {
    setPendingHubSkills((prev) =>
      prev.some((item) => item.skill_name === skill.skill_name)
        ? prev
        : [...prev, skill],
    );
  };

  const handlePickAgentSkill = (skill: PickedAgentSkill) => {
    setPendingCopySkills((prev) =>
      prev.some((item) => item.slug === skill.slug)
        ? prev
        : [...prev, { agent_id: skill.agent_id, slug: skill.slug }],
    );
    setFileContents((prev) =>
      upsertComposerFile(prev, {
        name: `skills/${skill.slug}/SKILL.md`,
        content: skill.content,
      }),
    );
  };

  const handlePickCatalogSubagent = (subagent: PickedCatalogSubagent) => {
    setFileContents((prev) =>
      upsertComposerFile(prev, {
        name: `agents/${subagent.slug}.md`,
        content: subagent.content,
      }),
    );
  };

  const selectedSubagentSlugs = useMemo(
    () => new Set(subagentFiles.map((item) => item.slug)),
    [subagentFiles],
  );

  const title = source
    ? t("experts.createDrawerTitle", {
        name: sourceTitle(source, lang),
      })
    : "";

  const orderedConfigNames = new Set([
    ...filterConfigMdFiles(configFiles.map(({ name }) => ({ path: name }))).map(
      (path) => path.slice(1),
    ),
    ...configFiles.map(({ name }) => name),
  ]);

  const skillPreviewGroups = skillGroups.map((group) => ({
    key: group.name,
    label: `${group.emoji ?? ""} ${group.displayName}`.trim(),
    path: `skills/${group.name}/`,
    description: group.description,
    files: group.files.map((f) => {
      const skillBasename = f.name.replace(`skills/${group.name}/`, "");
      return {
        key: f.name,
        label: metaForFile(skillBasename, t).label,
        path: skillBasename,
        content: f.content,
      };
    }),
  }));

  const subagentPreviewFiles = subagentFiles.map((subagent) => ({
    key: subagent.slug,
    label: `${subagent.emoji ?? ""} ${subagent.name}`.trim(),
    path: `agents/${subagent.slug}.md`,
    description: subagent.description,
    content: subagent.file.content,
  }));

  return (
    <Drawer
      open={open}
      title={title}
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
            loading={submitting}
            disabled={createBlocked}
            title={hasNoModels ? t("experts.noModelsWarning") : undefined}
            onClick={() => void handleCreate()}
          >
            {submitting ? t("experts.creating") : t("common.create")}
          </Button>
        </div>
      }
    >
      {hasNoModels && (
        <Alert
          type="warning"
          showIcon
          message={t("experts.noModelsWarning")}
          action={
            <a href="/admin/models" style={{ whiteSpace: "nowrap" }}>
              {t("experts.goToAdmin")}
            </a>
          }
          style={{ marginBottom: 16 }}
        />
      )}

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
              iconUrl={
                avatarPreview ??
                (avatarPresetTouched
                  ? expertPresetSrc(avatarPresetId ?? "default")
                  : sourceIcon(source).iconUrl)
              }
              iconName={sourceIcon(source).iconName}
              color={
                isCuratedPalette(colorPalette)
                  ? expertPaletteColor(colorPalette)
                  : colorPalette
              }
              disabled={submitting}
              onPick={(file) => {
                setAvatarFile(file);
                setAvatarPresetId(null);
                setAvatarPresetTouched(false);
                setAvatarPreview((prev) => {
                  if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
                  return URL.createObjectURL(file);
                });
              }}
              onSelectPreset={(presetId) => {
                setAvatarFile(null);
                setAvatarPresetId(presetId);
                setAvatarPresetTouched(true);
                setAvatarPreview((prev) => {
                  if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
                  return null;
                });
              }}
              onRemove={
                avatarFile || avatarPreview
                  ? () => {
                      setAvatarFile(null);
                      setAvatarPreview((prev) => {
                        if (prev?.startsWith("blob:"))
                          URL.revokeObjectURL(prev);
                        return null;
                      });
                    }
                  : undefined
              }
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
            rules={[{ required: true, message: t("experts.pleaseEnterName") }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="agent_id"
            label={t("experts.customIdLabel")}
            tooltip={t("experts.customIdHint")}
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

          <ExpertTextAssistField
            name="description"
            label={t("experts.agentDescription")}
            kind="expert.description"
          >
            <Input.TextArea autoSize={{ minRows: 2 }} />
          </ExpertTextAssistField>
          <AgentBackendFields
            backends={backends}
            backendsLoading={backendsLoading}
            backendChoice={backendChoice}
            pathMappings={pathMappings}
            rootDirMode="create"
            onAddPathMapping={addPathMapping}
            onRemovePathMapping={removePathMapping}
            onUpdatePathMapping={updatePathMapping}
          />
          <Form.Item
            name="conversation_mode"
            label={t("experts.defaultModeLabel")}
            tooltip={t("experts.defaultModeHint")}
            initialValue={DEFAULT_CONVERSATION_MODE}
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
        </ExpertDrawerSection>

        {/* ── Skills & resources ───────────────────────────── */}
        <ExpertDrawerSection id={SECTION_IDS.resources}>
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
          <ExpertComposerDefaultsFields />
        </ExpertDrawerSection>

        <ExpertDrawerSection id={SECTION_IDS.advanced} compact>
          <Form.Item name="welcome_message" noStyle>
            <WelcomeConfig
              key={sourceKey}
              ref={welcomeConfigRef}
              initialPrompts={templatePrompts}
              templateStatus={detailLoading ? "loading" : "ready"}
              disabled={detailLoading || submitting}
            />
          </Form.Item>
          <ExpertSettingsDrawer
            title={t("experts.expertFilesAccessTitle")}
            summary={t("experts.expertFilesAccessSummary")}
          >
            <Form.Item
              label={
                <ExpertFieldLabel
                  label={t("experts.mdFilesTitle")}
                  tooltip={t("experts.promptFilesHint")}
                />
              }
            >
              {detailLoading ? (
                <div style={{ textAlign: "center", padding: "16px 0" }}>
                  <Spin size="small" />
                </div>
              ) : (
                <div className={expertDrawerStyles.rowList}>
                  {[...orderedConfigNames].map((name) => {
                    const meta = metaForFile(name, t);
                    return (
                      <ExpertResourceRow
                        key={name}
                        icon={meta.icon}
                        iconStyle={{
                          color: meta.color,
                          background: `${meta.color}1a`,
                        }}
                        label={meta.label}
                        secondary={name}
                        hint={t("experts.editFile")}
                        onOpen={() => setLocalEditPath(name)}
                        menuLabel={t("common.more")}
                      />
                    );
                  })}
                </div>
              )}
            </Form.Item>
            {/* Skills list (template preview + pending installs), inline previews kept */}
            <Form.Item
              tooltip={t("experts.skillFilesEditHint")}
              label={
                <ExpertFieldLabel
                  label={t("experts.skillFilesTitle", {
                    count: skillGroups.length + pendingHubSkills.length,
                  })}
                  action={t("experts.addSkill")}
                  onAction={() => setSkillPickerOpen(true)}
                />
              }
            >
              {detailLoading ? (
                <div style={{ textAlign: "center", padding: "16px 0" }}>
                  <Spin size="small" />
                </div>
              ) : skillGroups.length === 0 && pendingHubSkills.length === 0 ? (
                <div className={expertDrawerStyles.rowEmpty}>
                  {t("experts.noSkillFiles")}
                </div>
              ) : (
                <>
                  {skillPreviewGroups.map((group) => (
                    <div key={group.key} style={{ marginBottom: 12 }}>
                      <div className={expertDrawerStyles.subgroupTitle}>
                        {group.label}
                        <Button
                          type="link"
                          size="small"
                          danger
                          style={{ padding: 0, height: "auto", marginLeft: 8 }}
                          onClick={() => {
                            setFileContents((prev) =>
                              removeComposerSkill(prev, group.key),
                            );
                            setPendingCopySkills((prev) =>
                              prev.filter((item) => item.slug !== group.key),
                            );
                          }}
                        >
                          {t("common.delete")}
                        </Button>
                      </div>
                      {group.description ? (
                        <p className={expertDrawerStyles.hint}>
                          {group.description}
                        </p>
                      ) : null}
                      <ExpertFilePreviewList
                        files={group.files}
                        onEdit={(key) => setLocalEditPath(key)}
                        editLabel={t("experts.editFile")}
                      />
                    </div>
                  ))}
                  {pendingHubSkills.length > 0 ? (
                    <div className={expertDrawerStyles.rowList}>
                      {pendingHubSkills.map((skill) => (
                        <div
                          key={skill.skill_name}
                          className={expertDrawerStyles.row}
                        >
                          <div className={expertDrawerStyles.rowMain}>
                            <div className={expertDrawerStyles.rowMeta}>
                              <div className={expertDrawerStyles.rowLabel}>
                                {skill.display_name || skill.skill_name}
                              </div>
                              <div className={expertDrawerStyles.rowPath}>
                                {t("experts.hubSkillPending")}
                              </div>
                            </div>
                          </div>
                          <Button
                            type="link"
                            size="small"
                            danger
                            onClick={() =>
                              setPendingHubSkills((prev) =>
                                prev.filter(
                                  (item) =>
                                    item.skill_name !== skill.skill_name,
                                ),
                              )
                            }
                          >
                            {t("common.delete")}
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              )}
            </Form.Item>

            {/* Subagents list (template preview), inline previews kept */}
            <Form.Item
              tooltip={t("experts.subagentFilesEditHint")}
              label={
                <ExpertFieldLabel
                  label={t("experts.subagentFilesTitle", {
                    count: subagentFiles.length,
                  })}
                  action={t("experts.addSubagent")}
                  onAction={() => setSubagentPickerOpen(true)}
                />
              }
            >
              {subagentFiles.length === 0 ? (
                <div className={expertDrawerStyles.rowEmpty}>
                  {t("experts.noSubagentFiles")}
                </div>
              ) : (
                subagentPreviewFiles.map((subagent) => (
                  <div key={subagent.key} style={{ marginBottom: 12 }}>
                    <div className={expertDrawerStyles.subgroupTitle}>
                      {subagent.label}
                      <span style={{ marginLeft: 8 }}>
                        <Button
                          type="link"
                          size="small"
                          style={{ padding: 0, height: "auto" }}
                          onClick={() =>
                            setLocalEditPath(
                              subagentFiles.find(
                                (item) => item.slug === subagent.key,
                              )?.file.name ?? subagent.key,
                            )
                          }
                        >
                          {t("experts.editFile")}
                        </Button>
                        <Button
                          type="link"
                          size="small"
                          danger
                          style={{ padding: 0, height: "auto" }}
                          onClick={() =>
                            setFileContents((prev) =>
                              removeComposerSubagent(prev, subagent.key),
                            )
                          }
                        >
                          {t("common.delete")}
                        </Button>
                      </span>
                    </div>
                    {subagent.description ? (
                      <p className={expertDrawerStyles.hint}>
                        {subagent.description}
                      </p>
                    ) : null}
                    <ExpertFilePreviewList files={[subagent]} />
                  </div>
                ))
              )}
            </Form.Item>
            {sharingAvailable ? (
              <ResourceVisibilityFormItem
                allowOwner
                visibility={expertVisibility}
                groupIds={expertGroupIds}
                tooltip={t("experts.visibilityHint")}
                onChange={(next) => {
                  setExpertVisibility(next.visibility);
                  setExpertGroupIds(
                    next.visibility === "groups" ? next.groupIds : [],
                  );
                }}
              />
            ) : null}
            <AgentTrajectoryField />
            <SkillSourcePickerModal
              open={skillPickerOpen}
              excludeSlugs={selectedSkillSlugs}
              onClose={() => setSkillPickerOpen(false)}
              onPickHub={handlePickHubSkill}
              onPickAgentSkill={handlePickAgentSkill}
            />
            <SubagentSourcePickerModal
              open={subagentPickerOpen}
              excludeSlugs={selectedSubagentSlugs}
              onClose={() => setSubagentPickerOpen(false)}
              onPick={handlePickCatalogSubagent}
            />
            <FileEditModal
              open={!!localEditPath}
              filePath={localEditPath}
              localValue={localEditFile?.content ?? ""}
              onClose={() => {
                setLocalEditPath(null);
              }}
              onSaved={() => undefined}
              onLocalSave={(content) => {
                if (!localEditPath) return;
                setFileContents((prev) =>
                  upsertComposerFile(prev, { name: localEditPath, content }),
                );
              }}
            />
          </ExpertSettingsDrawer>
          <ExpertSettingsDrawer
            title={t("experts.advancedOptions")}
            summary={t("experts.runtimeSettingsSummary")}
            fields={runtimeSettingsFields}
            open={runtimeOpen}
            onOpenChange={setRuntimeOpen}
          >
            <AgentAdvancedConfigFields grouped />
          </ExpertSettingsDrawer>
        </ExpertDrawerSection>
      </Form>
    </Drawer>
  );
}
