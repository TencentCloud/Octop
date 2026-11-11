import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, Collapse, Drawer, Form, Input, Select, Spin } from "antd";
import { message } from "@/utils/antdMessage";

import { request } from "../../../api/request";
import {
  teamsApi,
  type TeamRecord,
  type TeamTemplateFile,
} from "../../../api/modules/teams";
import { octopAgentsApi } from "../../../api/modules/octopAgents";
import {
  avatarPickerStyles,
  expertPresetSrc,
  isUploadedAvatarUrl,
  ResourceAvatarPicker,
  splitExpertAvatarUrl,
  TEAM_AVATAR_PRESETS,
} from "../../../components/AvatarPicker";
import { TextAssistBar } from "../../../components/TextAssistBar";
import type { OctopAgent } from "../../../context/AgentContext";
import { useAgentFormResources } from "../../../hooks/useAgentFormResources";
import { apiErrorMessage } from "../../../utils/apiError";
import {
  buildModelSelectOptions,
  defaultModelFromForm,
  defaultModelToForm,
  MODEL_AUTO_VALUE,
} from "../../../utils/modelOptions";
import { TEAM_AVATAR_URL, TEAM_ICON_NAME } from "../../../utils/teamAgent";
import ExpertAgentAvatar from "../../Chat/components/ExpertAgentAvatar";
import {
  buildBackendSpec,
  DEFAULT_BACKEND,
  ensureBubblewrapAfterProbe,
  ensureBwrapMessage,
  ensureBwrapToastKind,
  parseBackendSpec,
  probeRootDir,
  rootDirProbeMessage,
  createWorkspaceSelection,
  shouldProbeRootDir,
  shouldProbeWorkspaceDir,
  validatePathMappings,
  type PathMapping,
} from "./agentBackendForm";
import AgentBackendFields from "./AgentBackendFields";
import { metaForFile } from "./iconForName";
import TeamMemberPicker, {
  mergeTeamPickerExperts,
  selectedRosterIds,
  type TeamMemberOption,
} from "./TeamMemberPicker";
import styles from "../index.module.less";

interface TeamDrawerProps {
  open: boolean;
  mode: "create" | "edit";
  team?: OctopAgent | null;
  experts: OctopAgent[];
  onClose: () => void;
  onSaved: (team: TeamRecord) => void;
  /** Edit mode: sample icon / upload already persisted; refresh the team card. */
  onIconUrlChange?: (agentId: string, iconUrl: string) => void;
}

interface TeamFormValues {
  name: string;
  description?: string;
  default_model: string;
  welcome_message?: string;
  member_ids: string[];
  backend_choice: string;
  composite_default?: string;
  root_dir?: string;
  workspace_dir?: string;
  workspace_dir_auto?: string;
}

export default function TeamDrawer({
  open,
  mode,
  team,
  experts,
  onClose,
  onSaved,
  onIconUrlChange,
}: TeamDrawerProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<TeamFormValues>();
  const { models, modelsLoading, backends, backendsLoading } =
    useAgentFormResources(open);
  const [submitting, setSubmitting] = useState(false);
  const [pathMappings, setPathMappings] = useState<PathMapping[]>([]);
  const [templateFiles, setTemplateFiles] = useState<TeamTemplateFile[]>([]);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [rosterExtras, setRosterExtras] = useState<TeamMemberOption[]>([]);
  const [iconUrl, setIconUrl] = useState<string | null>(TEAM_AVATAR_URL);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const iconTouchedRef = useRef(false);
  const pickerExperts = useMemo(
    () => mergeTeamPickerExperts(experts, rosterExtras),
    [experts, rosterExtras],
  );
  const backendChoice =
    Form.useWatch("backend_choice", form) ?? DEFAULT_BACKEND;

  useEffect(() => {
    if (!open) {
      iconTouchedRef.current = false;
      setRosterExtras([]);
      setPathMappings([]);
      return;
    }
    iconTouchedRef.current = false;
    if (mode === "edit" && team) {
      form.setFieldsValue({
        name: team.name,
        description: team.description ?? "",
        default_model: defaultModelToForm(team.default_model),
        welcome_message: team.welcome_message ?? "",
        member_ids: team.member_ids ?? [],
        backend_choice: DEFAULT_BACKEND,
        composite_default: DEFAULT_BACKEND,
        root_dir: undefined,
        workspace_dir: "",
      });
      setPathMappings([]);
      setIconUrl(team.icon_url?.trim() || TEAM_AVATAR_URL);
      setAvatarFile(null);
      let cancelled = false;
      void request<{
        config?: { backend?: unknown; workspace_dir?: unknown };
      }>(`/agents/${team.agent_id}`)
        .then((detail) => {
          if (cancelled) return;
          const cfg = detail.config ?? {};
          const parsed = parseBackendSpec(cfg.backend);
          const workspace =
            typeof cfg.workspace_dir === "string" ? cfg.workspace_dir : "";
          setPathMappings(parsed.pathMappings);
          form.setFieldsValue({
            backend_choice: parsed.backendChoice,
            composite_default: parsed.compositeDefault,
            root_dir: parsed.rootDir,
            workspace_dir: workspace,
          });
        })
        .catch(() => {
          if (!cancelled) setPathMappings([]);
        });
      void teamsApi
        .get(team.agent_id)
        .then((record) => {
          if (cancelled) return;
          form.setFieldsValue({
            name: record.name,
            description: record.description ?? "",
            default_model: defaultModelToForm(record.default_model),
            welcome_message: record.welcome_message ?? "",
            member_ids: record.members.map((member) => member.agent_id),
          });
          if (!iconTouchedRef.current) {
            setIconUrl(record.icon_url?.trim() || TEAM_AVATAR_URL);
          }
          setRosterExtras(
            record.members.map((member) => ({
              agent_id: member.agent_id,
              name: member.name,
              color: member.color,
              icon_name: member.icon_name,
              icon_url: member.icon_url,
              kind: "expert",
              is_shared: member.is_shared,
              is_owner: true,
            })),
          );
        })
        .catch(() => {
          if (!cancelled) setRosterExtras([]);
        });
      return () => {
        cancelled = true;
      };
    }
    form.setFieldsValue({
      name: "",
      description: "",
      default_model: MODEL_AUTO_VALUE,
      welcome_message: t("experts.teams.welcomeDefault"),
      member_ids: [],
      backend_choice: DEFAULT_BACKEND,
      composite_default: DEFAULT_BACKEND,
      root_dir: undefined,
      workspace_dir: "",
      workspace_dir_auto: "",
    });
    setPathMappings([]);
    setIconUrl(TEAM_AVATAR_URL);
    setAvatarFile(null);
    setRosterExtras([]);
  }, [form, mode, open, t, team]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setTemplateLoading(true);
    teamsApi
      .templateFiles()
      .then((files) => {
        if (!cancelled) setTemplateFiles(files);
      })
      .catch(() => {
        if (!cancelled) setTemplateFiles([]);
      })
      .finally(() => {
        if (!cancelled) setTemplateLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const hasNoModels = !modelsLoading && models.length === 0;
  const blocked = submitting || hasNoModels;
  const { imageUrl, presetId } = splitExpertAvatarUrl(iconUrl);

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
      prev.map((mapping, i) =>
        i === index ? { ...mapping, [field]: value } : mapping,
      ),
    );

  const handleSubmit = async () => {
    const values = await form.validateFields();
    if (mode === "create" && values.backend_choice === "composite") {
      const pathError = validatePathMappings(pathMappings, t);
      if (pathError) {
        message.error(pathError);
        return;
      }
    }
    if (
      mode === "create" &&
      shouldProbeRootDir(values.backend_choice, values.root_dir)
    ) {
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
    const autoWorkspaceDir =
      mode === "create" ? form.getFieldValue("workspace_dir_auto") : undefined;
    const workspaceSelection =
      mode === "create"
        ? createWorkspaceSelection({
            backendChoice: values.backend_choice,
            rootDir: values.root_dir,
            workspaceDir: values.workspace_dir,
            autoWorkspaceDir,
          })
        : { workspaceDir: undefined, agentId: undefined };
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
    const body = {
      name: values.name.trim(),
      description: values.description?.trim() || null,
      default_model: defaultModelFromForm(values.default_model),
      icon_name: TEAM_ICON_NAME,
      icon_url: avatarFile
        ? TEAM_AVATAR_URL
        : iconUrl?.trim() || TEAM_AVATAR_URL,
      welcome_message: values.welcome_message?.trim() || null,
      member_ids: selectedRosterIds(values.member_ids, pickerExperts),
    };
    const backendSpec = buildBackendSpec(
      values.backend_choice,
      values.composite_default ?? DEFAULT_BACKEND,
      pathMappings,
      values.root_dir,
    );
    setSubmitting(true);
    let bwrapToast: { kind: "success" | "warning"; text: string } | null = null;
    try {
      if (
        mode === "create" &&
        shouldProbeRootDir(values.backend_choice, values.root_dir)
      ) {
        const bwrap = await ensureBubblewrapAfterProbe();
        const kind = ensureBwrapToastKind(bwrap.status);
        if (kind !== "none") {
          bwrapToast = { kind, text: ensureBwrapMessage(bwrap, t) };
        }
      }
      const saved =
        mode === "edit" && team
          ? await teamsApi.update(team.agent_id, body)
          : await teamsApi.create({
              ...body,
              name: body.name,
              member_ids: body.member_ids,
              ...(workspaceSelection.agentId
                ? { agent_id: workspaceSelection.agentId }
                : {}),
              config: {
                backend: backendSpec,
                ...(workspaceDir ? { workspace_dir: workspaceDir } : {}),
              },
            });
      if (avatarFile) {
        try {
          const result = await octopAgentsApi.uploadAvatar(
            saved.agent_id,
            avatarFile,
          );
          saved.icon_url = result.icon_url;
        } catch {
          message.warning(t("experts.teams.avatarUploadLater"));
        }
      }
      message.success(
        mode === "edit"
          ? t("experts.teams.updated")
          : t("experts.teams.created"),
      );
      if (bwrapToast?.kind === "success") {
        message.success(bwrapToast.text);
      } else if (bwrapToast?.kind === "warning") {
        message.warning(bwrapToast.text);
      }
      onSaved(saved);
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("experts.createFailed"), t));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      title={
        mode === "edit"
          ? t("experts.teams.editTitle")
          : t("experts.teams.createTitle")
      }
      open={open}
      onClose={onClose}
      width={600}
      destroyOnHidden
      footer={
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className={styles.drawerCancelBtn} onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button
            className={styles.drawerSaveBtn}
            onClick={() => void handleSubmit()}
            disabled={blocked}
            title={hasNoModels ? t("experts.noModelsWarning") : undefined}
          >
            {submitting
              ? t("experts.creating")
              : mode === "edit"
              ? t("common.save")
              : t("common.create")}
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
            <a href="/admin/models" style={{ whiteSpace: "nowrap" }}>
              {t("experts.goToAdmin")}
            </a>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      <Form form={form} layout="vertical" size="middle">
        <Form.Item
          label={t("experts.avatar")}
          className={avatarPickerStyles.formItem}
        >
          <ResourceAvatarPicker
            imageUrl={imageUrl}
            presetId={presetId === "team-host" ? null : presetId}
            presets={TEAM_AVATAR_PRESETS}
            disabled={submitting || avatarBusy}
            onPick={(file) => {
              if (mode === "edit" && team) {
                void (async () => {
                  iconTouchedRef.current = true;
                  setAvatarBusy(true);
                  try {
                    const result = await octopAgentsApi.uploadAvatar(
                      team.agent_id,
                      file,
                    );
                    setIconUrl(result.icon_url);
                    setAvatarFile(null);
                    onIconUrlChange?.(team.agent_id, result.icon_url);
                  } catch (err) {
                    message.error(
                      apiErrorMessage(err, t("experts.avatarUploadFailed"), t),
                    );
                    throw err;
                  } finally {
                    setAvatarBusy(false);
                  }
                })();
                return;
              }
              iconTouchedRef.current = true;
              setAvatarFile(file);
              setIconUrl(URL.createObjectURL(file));
            }}
            onSelectPreset={(id) => {
              void (async () => {
                const nextUrl = id ? expertPresetSrc(id) : TEAM_AVATAR_URL;
                const previousUrl = iconUrl;
                iconTouchedRef.current = true;
                setAvatarFile(null);
                setIconUrl(nextUrl);
                if (!(mode === "edit" && team)) return;
                setAvatarBusy(true);
                try {
                  if (isUploadedAvatarUrl(previousUrl)) {
                    try {
                      await octopAgentsApi.deleteAvatar(team.agent_id);
                    } catch {
                      // Preset path still wins when the portrait is saved.
                    }
                  }
                  const saved = await teamsApi.update(team.agent_id, {
                    icon_url: nextUrl,
                  });
                  const applied = saved.icon_url?.trim() || nextUrl;
                  setIconUrl(applied);
                  onIconUrlChange?.(team.agent_id, applied);
                } catch (err) {
                  setIconUrl(previousUrl);
                  message.error(
                    apiErrorMessage(err, t("experts.avatarUploadFailed"), t),
                  );
                } finally {
                  setAvatarBusy(false);
                }
              })();
            }}
            onRemove={
              imageUrl || avatarFile
                ? () => {
                    void (async () => {
                      const previousUrl = iconUrl;
                      iconTouchedRef.current = true;
                      setAvatarFile(null);
                      setIconUrl(TEAM_AVATAR_URL);
                      if (!(mode === "edit" && team)) return;
                      setAvatarBusy(true);
                      try {
                        if (isUploadedAvatarUrl(previousUrl)) {
                          await octopAgentsApi.deleteAvatar(team.agent_id);
                        } else {
                          await teamsApi.update(team.agent_id, {
                            icon_url: TEAM_AVATAR_URL,
                          });
                        }
                        onIconUrlChange?.(team.agent_id, TEAM_AVATAR_URL);
                      } catch (err) {
                        setIconUrl(previousUrl);
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
                  }
                : undefined
            }
            renderPreview={({ displayUrl, presetId: selected, hasPhoto }) => (
              <ExpertAgentAvatar
                iconUrl={
                  hasPhoto
                    ? displayUrl
                    : selected
                    ? expertPresetSrc(selected)
                    : iconUrl
                }
                iconName={TEAM_ICON_NAME}
                size={56}
              />
            )}
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
          name="description"
          label={t("experts.agentDescription")}
          className={styles.textAssistField}
        >
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} />
        </Form.Item>
        <TextAssistBar
          kind="team.description"
          getName={() => String(form.getFieldValue("name") ?? "")}
          getText={() => String(form.getFieldValue("description") ?? "")}
          onApply={(text) => form.setFieldsValue({ description: text })}
        />
        <Form.Item
          name="welcome_message"
          label={t("experts.welcomeMessageTitle")}
          tooltip={
            mode === "edit"
              ? t("experts.editWelcomeHint")
              : t("experts.createWelcomeHint")
          }
          className={styles.textAssistField}
        >
          <Input.TextArea
            autoSize={{ minRows: 2, maxRows: 5 }}
            placeholder={t("experts.welcomeMessagePlaceholder")}
          />
        </Form.Item>
        <TextAssistBar
          kind="team.welcome_message"
          getName={() => String(form.getFieldValue("name") ?? "")}
          getText={() => String(form.getFieldValue("welcome_message") ?? "")}
          onApply={(text) => form.setFieldsValue({ welcome_message: text })}
        />
        <Form.Item name="default_model" label={t("experts.defaultModelLabel")}>
          <Select
            loading={modelsLoading}
            options={buildModelSelectOptions(
              models,
              t("experts.defaultModelAuto"),
            )}
            placeholder={t("experts.defaultModelPlaceholder")}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>
        <AgentBackendFields
          backends={backends}
          backendsLoading={backendsLoading}
          backendChoice={backendChoice}
          pathMappings={pathMappings}
          rootDirMode={mode === "edit" ? "edit" : "create"}
          disabled={mode === "edit"}
          onAddPathMapping={addPathMapping}
          onRemovePathMapping={removePathMapping}
          onUpdatePathMapping={updatePathMapping}
        />
        <Form.Item
          name="member_ids"
          label={t("experts.teams.members")}
          extra={t("experts.teams.membersHint")}
          rules={[
            {
              validator: async (_, value: string[]) => {
                if (selectedRosterIds(value, pickerExperts).length < 2) {
                  throw new Error(t("experts.teams.membersMin"));
                }
              },
            },
          ]}
        >
          <TeamMemberPicker experts={pickerExperts} />
        </Form.Item>
      </Form>

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
          {t("experts.teams.mdFilesHint")}
        </p>
        {templateLoading ? (
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            <Spin size="small" />
          </div>
        ) : (
          <Collapse
            size="small"
            items={templateFiles.map((file) => {
              const meta = metaForFile(file.name, t);
              return {
                key: file.name,
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
                      {file.name}
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
                    {file.content}
                  </pre>
                ),
              };
            })}
          />
        )}
      </div>
    </Drawer>
  );
}
