import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Button,
  Collapse,
  Drawer,
  Form,
  Input,
  Select,
  Switch,
} from "antd";
import { message } from "@/utils/antdMessage";

import {
  acpApi,
  acpSessionModeText,
  catalogOffersUnattendedMode,
  isUnattendedSessionMode,
  permissionForSessionMode,
} from "../../../api/modules/acp";
import { useAcpSessionModes } from "../../../hooks/useAcpSessionModes";
import { skillPackagesApi } from "../../../api/modules/skillPackages";
import {
  managedAgentsApi,
  managedWorkspaceDir,
  type ManagedQuickPrompt,
  type ManagedWorkspaceFile,
} from "../../../api/modules/managedAgents";
import { octopAgentsApi } from "../../../api/modules/octopAgents";
import type { ResourceVisibilityMode } from "../../../api/modules/userGroups";
import {
  avatarPickerStyles,
  expertPresetSrc,
} from "../../../components/AvatarPicker";
import BetaBadge from "../../../components/BetaBadge";
import ExpertColorPicker from "../../../components/ExpertColorPicker";
import { ResourceVisibilityFormItem } from "../../../components/ResourceVisibilityFields";
import { TextAssistBar } from "../../../components/TextAssistBar";
import { apiErrorMessage } from "../../../utils/apiError";
import { expertPaletteColor } from "../../../utils/expertColor";
import {
  DEFAULT_PALETTE,
  isCuratedPalette,
} from "../../../styles/themePalettes";
import AgentTrajectoryField from "./AgentTrajectoryField";
import ExpertAvatarPicker from "./ExpertAvatarPicker";
import ExpertComposerDefaultsFields from "./ExpertComposerDefaultsFields";
import FileEditModal from "./FileEditModal";
import { metaForFile } from "./iconForName";
import ManagedRunnerPicker from "./ManagedRunnerPicker";
import MoreConfigCollapse from "./MoreConfigCollapse";
import RootDirSelect from "./RootDirSelect";
import WelcomeConfig, { type WelcomeConfigRef } from "./WelcomeConfig";
import {
  normalizeQuickPrompts,
  serializeQuickPrompts,
} from "./welcomeManifest";
import styles from "../index.module.less";

interface ManagedDrawerProps {
  open: boolean;
  onClose: () => void;
  onCreated: (agentId: string) => void;
}

interface FormValues {
  name: string;
  runner: string;
  workspace_dir: string;
  description?: string;
  welcome_message?: string;
  agent_id?: string;
  enable_trajectory?: boolean;
  skill_package_ids?: string[];
  knowledge_base_ids?: string[];
  mcp_servers?: string[];
  permission_mode?: boolean;
  session_mode?: string;
}

function storedColor(palette: string): string {
  return isCuratedPalette(palette) ? expertPaletteColor(palette) : palette;
}

const AGENT_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

function mintAgentId(): string {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => AGENT_ID_ALPHABET[byte & 31]).join("");
}

function WorkspaceDirField({
  value,
  onChange,
  onUserEdit,
}: {
  value?: string;
  onChange?: (value: string) => void;
  onUserEdit: () => void;
}) {
  return (
    <RootDirSelect
      value={value}
      onChange={(next) => {
        onUserEdit();
        onChange?.(next);
      }}
    />
  );
}

export default function ManagedDrawer({
  open,
  onClose,
  onCreated,
}: ManagedDrawerProps) {
  const { t, i18n } = useTranslation();
  const [form] = Form.useForm<FormValues>();
  const [runners, setRunners] = useState<string[]>([]);
  const [skillPackages, setSkillPackages] = useState<
    { id: string; name: string }[]
  >([]);
  const [skillPackagesLoading, setSkillPackagesLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [colorPalette, setColorPalette] = useState<string>(DEFAULT_PALETTE);
  const [visibility, setVisibility] = useState<ResourceVisibilityMode>("owner");
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [avatarPresetId, setAvatarPresetId] = useState<string | null>(null);
  const [avatarPresetTouched, setAvatarPresetTouched] = useState(false);
  const [templateState, setTemplateState] = useState<
    "loading" | "ready" | "error"
  >("loading");
  const [promptFiles, setPromptFiles] = useState<ManagedWorkspaceFile[]>([]);
  const [seedFiles, setSeedFiles] = useState<ManagedWorkspaceFile[]>([]);
  const [quickPrompts, setQuickPrompts] = useState<ManagedQuickPrompt[]>([]);
  const [editPath, setEditPath] = useState<string | null>(null);
  const [homeDir, setHomeDir] = useState("");
  const [previewId, setPreviewId] = useState("");
  const workspaceTouched = useRef(false);
  const welcomeRef = useRef<WelcomeConfigRef>(null);
  const watchedAgentId = Form.useWatch("agent_id", form);
  const watchedRunner = Form.useWatch("runner", form);
  const sessionModes = useAcpSessionModes(watchedRunner);

  useEffect(() => {
    if (!open || sessionModes.length === 0) return;
    const current = String(form.getFieldValue("session_mode") ?? "");
    if (sessionModes.some((mode) => mode.id === current)) return;
    const yolo = form.getFieldValue("permission_mode") === true;
    const preferred = yolo
      ? sessionModes.find((mode) => isUnattendedSessionMode(mode.id))
      : undefined;
    form.setFieldValue("session_mode", (preferred ?? sessionModes[0]).id);
  }, [form, open, sessionModes]);

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    form.setFieldsValue({
      enable_trajectory: true,
      permission_mode: false,
      session_mode: "",
    });
    setColorPalette(DEFAULT_PALETTE);
    setVisibility("owner");
    setGroupIds([]);
    setAvatarFile(null);
    setAvatarPresetId(null);
    setAvatarPresetTouched(false);
    setTemplateState("loading");
    workspaceTouched.current = false;
    setPreviewId(mintAgentId());
    setHomeDir("");
    setAvatarPreview((prev) => {
      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
      return null;
    });
    let cancelled = false;
    managedAgentsApi
      .template()
      .then((template) => {
        if (cancelled) return;
        setSeedFiles(template.files);
        setPromptFiles(template.files);
        setQuickPrompts(template.quick_prompts);
        setHomeDir(template.home || "");
        setTemplateState("ready");
      })
      .catch(() => {
        if (!cancelled) {
          setSeedFiles([]);
          setPromptFiles([]);
          setQuickPrompts([]);
          setTemplateState("error");
        }
      });
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
          message.error(
            apiErrorMessage(err, t("experts.managed.loadFailed"), t),
          );
        }
      });
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
  }, [form, open, t]);

  useEffect(() => {
    if (!open || !homeDir || !previewId || workspaceTouched.current) return;
    const custom = String(watchedAgentId ?? "").trim();
    form.setFieldValue(
      "workspace_dir",
      managedWorkspaceDir(homeDir, custom || previewId),
    );
  }, [form, homeDir, open, previewId, watchedAgentId]);

  const submit = async () => {
    let values: FormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    const customId = values.agent_id?.trim() || "";
    const agentId = customId || previewId || undefined;
    const workspace =
      values.workspace_dir.trim() ||
      (homeDir && agentId ? managedWorkspaceDir(homeDir, agentId) : "");
    const welcomeSnap = welcomeRef.current?.getSnapshot();
    const prompts =
      welcomeSnap && welcomeSnap.status === "ready" && welcomeSnap.dirty
        ? serializeQuickPrompts(welcomeSnap.data.quick_prompts)
        : undefined;
    const seedByName = new Map(
      seedFiles.map((file) => [file.name, file.content]),
    );
    const fileOverrides = promptFiles.filter(
      (file) => seedByName.get(file.name) !== file.content,
    );
    setSaving(true);
    try {
      const created = await managedAgentsApi.create({
        name: values.name.trim(),
        runner: values.runner,
        workspace_dir: workspace,
        description: values.description?.trim() || undefined,
        welcome_message: values.welcome_message?.trim() || undefined,
        agent_id: agentId,
        color: storedColor(colorPalette),
        icon_url: avatarFile
          ? undefined
          : expertPresetSrc(avatarPresetId ?? "default"),
        enable_trajectory: values.enable_trajectory === true,
        permission_mode: permissionForSessionMode(
          sessionModes,
          values.session_mode ?? "",
          values.permission_mode === true,
        ),
        ...(sessionModes.length > 0 && values.session_mode
          ? { session_mode: values.session_mode }
          : {}),
        skill_package_ids: values.skill_package_ids ?? [],
        knowledge_base_ids: values.knowledge_base_ids ?? [],
        mcp_servers: values.mcp_servers ?? [],
        visibility,
        group_ids: visibility === "groups" ? groupIds : [],
        ...(prompts ? { quick_prompts: prompts } : {}),
        ...(fileOverrides.length ? { file_overrides: fileOverrides } : {}),
      });
      if (avatarFile) {
        try {
          await octopAgentsApi.uploadAvatar(created.agent_id, avatarFile);
        } catch {
          message.warning(t("experts.avatarUploadLater"));
        }
      }
      onCreated(created.agent_id);
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("experts.managed.createFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      title={
        <span className={styles.titleWithBeta}>
          {t("experts.managed.createTitle")}
          <BetaBadge />
        </span>
      }
      open={open}
      onClose={onClose}
      width={600}
      destroyOnHidden
      className={styles.expertDrawer}
      rootClassName={styles.expertDrawerRoot}
      footer={
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="primary" loading={saving} onClick={() => void submit()}>
            {t("experts.managed.create")}
          </Button>
        </div>
      }
    >
      {runners.length === 0 ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t("experts.managed.noRunners")}
        />
      ) : null}
      <Form form={form} layout="vertical" size="middle" requiredMark={false}>
        <Form.Item
          label={t("experts.avatar")}
          className={avatarPickerStyles.formItem}
        >
          <ExpertAvatarPicker
            iconUrl={
              avatarPreview ?? expertPresetSrc(avatarPresetId ?? "default")
            }
            color={storedColor(colorPalette)}
            disabled={saving}
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
              avatarFile || avatarPreview || avatarPresetTouched
                ? () => {
                    setAvatarFile(null);
                    setAvatarPresetId(null);
                    setAvatarPresetTouched(false);
                    setAvatarPreview((prev) => {
                      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
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
          kind="expert.description"
          getName={() => String(form.getFieldValue("name") ?? "")}
          getText={() => String(form.getFieldValue("description") ?? "")}
          onApply={(text) => form.setFieldsValue({ description: text })}
        />
        <Form.Item
          name="welcome_message"
          label={t("experts.welcomeMessageTitle")}
          tooltip={t("experts.createWelcomeHint")}
          className={styles.textAssistField}
        >
          <Input.TextArea
            rows={3}
            placeholder={t("experts.welcomeMessagePlaceholder")}
          />
        </Form.Item>
        <TextAssistBar
          kind="expert.welcome_message"
          getName={() => String(form.getFieldValue("name") ?? "")}
          getText={() => String(form.getFieldValue("welcome_message") ?? "")}
          onApply={(text) => form.setFieldsValue({ welcome_message: text })}
        />
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
            { required: true, message: t("experts.managed.runnerRequired") },
          ]}
        >
          <ManagedRunnerPicker runners={runners} />
        </Form.Item>
        {sessionModes.length > 0 ? (
          <Form.Item
            name="session_mode"
            label={t("chat.conversationMode.picker")}
            extra={t("experts.managed.sessionModeHint")}
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
            extra={t("experts.managed.yoloHint")}
          >
            <Switch />
          </Form.Item>
        )}
        <Form.Item
          name="workspace_dir"
          label={t("experts.workspaceDir")}
          rules={[
            { required: true, message: t("experts.managed.workspaceRequired") },
          ]}
        >
          <WorkspaceDirField
            onUserEdit={() => {
              workspaceTouched.current = true;
            }}
          />
        </Form.Item>
        <ResourceVisibilityFormItem
          allowOwner
          visibility={visibility}
          groupIds={groupIds}
          extra={t("experts.visibilityHint")}
          onChange={(next) => {
            setVisibility(next.visibility);
            setGroupIds(next.visibility === "groups" ? next.groupIds : []);
          }}
        />
        <Form.Item
          name="skill_package_ids"
          label={t("experts.skillPackagesLabel")}
          extra={t("experts.managedSkillPackagesHint")}
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
        <ExpertComposerDefaultsFields />
        <MoreConfigCollapse>
          <Form.Item
            name="agent_id"
            label={t("experts.customIdLabel")}
            extra={t("experts.customIdHint")}
            rules={[
              {
                validator: (_: unknown, value: string | undefined) => {
                  const next = value?.trim() ?? "";
                  if (!next) return Promise.resolve();
                  if (
                    !/^[a-zA-Z0-9][a-zA-Z0-9_-]{1,62}[a-zA-Z0-9]$/.test(next)
                  ) {
                    return Promise.reject(
                      new Error(t("experts.customIdInvalid")),
                    );
                  }
                  if (
                    ["api", "admin", "agents", "experts"].includes(
                      next.toLowerCase(),
                    )
                  ) {
                    return Promise.reject(
                      new Error(t("experts.customIdReserved", { id: next })),
                    );
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <Input placeholder={t("experts.customIdPlaceholder")} allowClear />
          </Form.Item>
          <AgentTrajectoryField />
          <Collapse
            ghost
            className={styles.drawerCollapse}
            items={[
              {
                key: "pageConfig",
                label: t("experts.pageConfigTitle"),
                children:
                  templateState !== "ready" ? (
                    <div className={styles.welcomeConfigLoading}>
                      {templateState === "error"
                        ? t("experts.managed.templateFailed")
                        : t("common.loading")}
                    </div>
                  ) : (
                    <WelcomeConfig
                      ref={welcomeRef}
                      initialPrompts={normalizeQuickPrompts(quickPrompts)}
                      disabled={saving}
                    />
                  ),
              },
              {
                key: "configFiles",
                label: t("experts.mdFilesTitle"),
                children: (
                  <>
                    <p className={styles.managedFileHint}>
                      {t("experts.mdFilesEditHint")}
                    </p>
                    {templateState !== "ready" ? (
                      <div className={styles.welcomeConfigLoading}>
                        {templateState === "error"
                          ? t("experts.managed.templateFailed")
                          : t("common.loading")}
                      </div>
                    ) : (
                      <Collapse
                        size="small"
                        items={promptFiles.map((file) => {
                          const meta = metaForFile(file.name, t);
                          return {
                            key: file.name,
                            label: (
                              <span className={styles.managedFileLabel}>
                                <span>{meta.label}</span>
                                <span className={styles.managedFileName}>
                                  {file.name}
                                </span>
                              </span>
                            ),
                            extra: (
                              <Button
                                type="link"
                                size="small"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setEditPath(file.name);
                                }}
                              >
                                {t("experts.editFile")}
                              </Button>
                            ),
                            children: (
                              <pre className={styles.managedFilePreview}>
                                {file.content}
                              </pre>
                            ),
                          };
                        })}
                      />
                    )}
                  </>
                ),
              },
            ]}
          />
        </MoreConfigCollapse>
      </Form>
      <FileEditModal
        open={editPath !== null}
        filePath={editPath ? `/${editPath}` : null}
        localValue={
          promptFiles.find((file) => file.name === editPath)?.content ?? ""
        }
        onClose={() => setEditPath(null)}
        onSaved={() => setEditPath(null)}
        onLocalSave={(content) => {
          if (!editPath) return;
          setPromptFiles((prev) =>
            prev.map((file) =>
              file.name === editPath ? { ...file, content } : file,
            ),
          );
        }}
      />
    </Drawer>
  );
}
