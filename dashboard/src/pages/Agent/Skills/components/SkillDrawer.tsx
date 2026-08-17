import { useCallback, useEffect, useState } from "react";
import { Drawer, Form, Input, Button, Segmented, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";

import { MinusCircle, PanelLeftOpen, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FormInstance } from "antd";
import EmojiPicker from "../../../../components/EmojiPicker";
import Markdown from "../../../../components/Markdown/LazyMarkdown";
import { request } from "../../../../api/request";
import { splitMarkdownFrontmatter } from "../../../../utils/markdown";
import { withFromWorkspace } from "../../../../utils/fromWorkspace";
import { useListPanelCollapsed } from "../../../../hooks/useListPanelCollapsed";
import type { SkillDetail } from "../useSkills";
import {
  isSkillManifestPath,
  skillDirectoryPath,
  skillManifestPath,
  DEFAULT_SKILL_EMOJI,
} from "../skillMarkdown";
import FileViewer from "../../Workspace/components/FileViewer";
import { getDocKind } from "../../Workspace/utils/docKind";
import { getMediaKind } from "../../Workspace/utils/mediaKind";
import { SkillFileTree } from "./SkillFileTree";
import styles from "./SkillDrawer.module.less";

export interface MetadataEntry {
  key: string;
  value: string;
}

/** Form fields for creating or viewing a skill. */
export interface SkillFormValues {
  name: string;
  description: string;
  /** Surfaced as ``metadata.octop.emoji`` in SKILL.md. */
  emoji: string;
  metadata: MetadataEntry[];
  body: string;
  content?: string;
  source?: string;
  path?: string;
}

export const OCTOP_EMOJI_META_KEY = "octop.emoji";

/**
 * The skill name doubles as the workspace directory slug, so only
 * filesystem-hostile characters are rejected - CJK and other Unicode
 * letters are allowed.
 */
const SKILL_NAME_PATTERN = /^(?!\.)[^\\/:*?"<>|\x00-\x1f]{1,64}$/;

export function isValidSkillName(name: string): boolean {
  return SKILL_NAME_PATTERN.test(name.trim());
}

function yamlQuote(value: string): string {
  if (!value) return '""';
  if (/[:#\n"'{}[\],&*?|>!%@`]/.test(value) || value.trim() !== value) {
    return JSON.stringify(value);
  }
  return value;
}

function setNested(
  obj: Record<string, unknown>,
  path: string,
  value: string,
): void {
  const parts = path.split(".").filter(Boolean);
  if (parts.length === 0) return;
  let cur: Record<string, unknown> = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i];
    const next = cur[part];
    if (!next || typeof next !== "object" || Array.isArray(next)) {
      cur[part] = {};
    }
    cur = cur[part] as Record<string, unknown>;
  }
  cur[parts[parts.length - 1]!] = value;
}

function metadataToYamlLines(
  meta: Record<string, unknown>,
  indent = 0,
): string[] {
  const pad = "  ".repeat(indent);
  const lines: string[] = [];
  for (const [key, value] of Object.entries(meta)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      lines.push(`${pad}${key}:`);
      lines.push(
        ...metadataToYamlLines(value as Record<string, unknown>, indent + 1),
      );
    } else {
      lines.push(`${pad}${key}: ${yamlQuote(String(value ?? ""))}`);
    }
  }
  return lines;
}

/** Split ``octop.emoji`` out of flattened metadata for the dedicated picker. */
export function parseSkillEmojiAndMetadata(
  pairs: MetadataEntry[] | undefined,
  fallback = DEFAULT_SKILL_EMOJI,
): { emoji: string; metadata: MetadataEntry[] } {
  let emoji = fallback;
  const metadata: MetadataEntry[] = [];
  for (const row of pairs ?? []) {
    if (row.key.trim() === OCTOP_EMOJI_META_KEY) {
      const value = row.value.trim();
      if (value) emoji = value;
      continue;
    }
    metadata.push(row);
  }
  return { emoji, metadata };
}

function withEmojiMetadata(
  pairs: MetadataEntry[] | undefined,
  emoji: string,
): MetadataEntry[] {
  const rest = (pairs ?? []).filter(
    (row) => row.key.trim() !== OCTOP_EMOJI_META_KEY,
  );
  const value = emoji.trim();
  if (!value) return rest;
  return [{ key: OCTOP_EMOJI_META_KEY, value }, ...rest];
}

function buildMetadataObject(
  pairs: MetadataEntry[] | undefined,
): Record<string, unknown> {
  const root: Record<string, unknown> = {};
  for (const row of pairs ?? []) {
    const key = row.key.trim();
    if (!key) continue;
    setNested(root, key, row.value.trim());
  }
  return root;
}

export function buildSkillMarkdown(values: SkillFormValues): string {
  const lines = [
    "---",
    `name: ${yamlQuote(values.name.trim())}`,
    `description: ${yamlQuote(values.description.trim())}`,
  ];
  const meta = buildMetadataObject(
    withEmojiMetadata(values.metadata, values.emoji ?? ""),
  );
  if (Object.keys(meta).length > 0) {
    lines.push("metadata:");
    lines.push(...metadataToYamlLines(meta, 1));
  }
  lines.push("---");
  const body = values.body.trim();
  return body ? `${lines.join("\n")}\n\n${body}\n` : `${lines.join("\n")}\n`;
}

function flattenMetadata(obj: unknown, prefix = ""): MetadataEntry[] {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return [];
  const out: MetadataEntry[] = [];
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      out.push(...flattenMetadata(value, path));
    } else {
      out.push({ key: path, value: String(value ?? "") });
    }
  }
  return out;
}

function yamlTopLevel(block: string, key: string): string {
  const re = new RegExp(`^${key}:\\s*(.+?)\\s*$`, "m");
  const match = block.match(re);
  if (!match) return "";
  return (match[1] || "").trim().replace(/^["']|["']$/g, "");
}

/** Apply full SKILL.md source back into structured form fields. */
function applySourceToFormFields(
  form: FormInstance<SkillFormValues>,
  content: string,
): void {
  const { raw, body } = splitMarkdownFrontmatter(content);
  const fm = raw ?? "";
  form.setFieldsValue({
    content,
    name: yamlTopLevel(fm, "name") || form.getFieldValue("name") || "",
    description:
      yamlTopLevel(fm, "description") ||
      form.getFieldValue("description") ||
      "",
    body,
  });
}

function parseSkillFormFromDetail(detail: SkillDetail): SkillFormValues {
  const fm = detail.frontmatter ?? {};
  const displayName =
    typeof fm.name === "string" && fm.name.trim() ? fm.name : detail.slug;
  const description =
    typeof fm.description === "string" ? fm.description : detail.description;
  const { emoji, metadata } = parseSkillEmojiAndMetadata(
    flattenMetadata(fm.metadata),
    detail.emoji?.trim() || DEFAULT_SKILL_EMOJI,
  );
  return {
    name: displayName,
    description,
    emoji,
    metadata,
    body: detail.body || "",
    content: detail.raw,
    source: detail.kind === "builtin" ? "builtin" : "workspace",
    path:
      detail.kind === "builtin"
        ? `/_builtin_skills/${detail.slug}/SKILL.md`
        : `/skills/${detail.slug}/SKILL.md`,
  };
}

type ViewTab = "preview" | "source";
type EditorTab = "form" | "source";

const FILE_TREE_COLLAPSED_KEY = "octop:skill-drawer-tree-collapsed";

interface SkillDrawerProps {
  open: boolean;
  editingSkill: SkillDetail | null;
  form: FormInstance<SkillFormValues>;
  onClose: () => void;
  onSubmit: (values: SkillFormValues) => void;
  /** When set, show skill directory file tree (workspace / built-in skills). */
  agentId?: string | null;
  /** Agent harness must be running for workspace file/tree APIs. */
  workspaceReady?: boolean;
}

export function SkillDrawer({
  open,
  editingSkill,
  form,
  onClose,
  onSubmit,
  agentId,
  workspaceReady = false,
}: SkillDrawerProps) {
  const { t } = useTranslation();
  const isCreate = !editingSkill;
  const [localEditMode, setLocalEditMode] = useState(false);
  const [viewTab, setViewTab] = useState<ViewTab>("preview");
  const [editorTab, setEditorTab] = useState<EditorTab>("form");
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [siblingContent, setSiblingContent] = useState("");
  const [siblingLoading, setSiblingLoading] = useState(false);
  const [siblingViewTab, setSiblingViewTab] = useState<ViewTab>("preview");
  const { collapsed: fileTreeCollapsed, toggle: toggleFileTreeCollapsed } =
    useListPanelCollapsed(FILE_TREE_COLLAPSED_KEY, { defaultCollapsed: true });

  const skillRoot = editingSkill ? skillDirectoryPath(editingSkill) : null;
  const showFileTree = Boolean(editingSkill && agentId && skillRoot);
  const isEdit = !!editingSkill && localEditMode;

  const handleSelectFilePath = useCallback(
    (path: string) => {
      if (isEdit && !isSkillManifestPath(path)) {
        message.warning(t("skills.finishEditBeforeSwitchFile"));
        return;
      }
      setSelectedFilePath(path);
    },
    [isEdit, t],
  );

  const viewingSkillMd =
    !selectedFilePath || isSkillManifestPath(selectedFilePath);

  const fieldsEditable = isCreate || isEdit;

  useEffect(() => {
    if (!open) {
      setLocalEditMode(false);
      setViewTab("preview");
      setEditorTab("form");
      setSelectedFilePath(null);
      setSiblingContent("");
      setSiblingViewTab("preview");
      return;
    }
    setLocalEditMode(false);
    setViewTab("preview");
    setEditorTab("form");
    setSiblingViewTab("preview");
    if (editingSkill) {
      setSelectedFilePath(skillManifestPath(editingSkill));
      const parsed = parseSkillFormFromDetail(editingSkill);
      form.setFieldsValue({
        ...parsed,
        source:
          editingSkill.kind === "builtin"
            ? t("skills.kindBuiltin")
            : t("skills.kindWorkspace"),
      });
      return;
    }
    setSelectedFilePath(null);
    form.setFieldsValue({
      name: "",
      description: "",
      emoji: DEFAULT_SKILL_EMOJI,
      metadata: [],
      body: t("skills.newSkillBodyTemplate"),
      content: "",
    });
  }, [editingSkill, form, open, t]);

  const loadSiblingFile = useCallback(
    async (path: string) => {
      if (!agentId || isSkillManifestPath(path)) return;
      setSiblingLoading(true);
      try {
        const data = await request<{ content: string }>(
          withFromWorkspace(
            `/agents/${agentId}/workspace/file?path=${encodeURIComponent(
              path,
            )}`,
          ),
        );
        setSiblingContent(data.content ?? "");
      } catch {
        setSiblingContent("");
      } finally {
        setSiblingLoading(false);
      }
    },
    [agentId],
  );

  useEffect(() => {
    if (
      !open ||
      !selectedFilePath ||
      viewingSkillMd ||
      !agentId ||
      !workspaceReady
    ) {
      return;
    }
    if (getMediaKind(selectedFilePath) || getDocKind(selectedFilePath)) {
      setSiblingContent("");
      setSiblingLoading(false);
      return;
    }
    void loadSiblingFile(selectedFilePath);
  }, [
    agentId,
    loadSiblingFile,
    open,
    selectedFilePath,
    viewingSkillMd,
    workspaceReady,
  ]);

  const resetToViewForm = () => {
    if (!editingSkill) return;
    const parsed = parseSkillFormFromDetail(editingSkill);
    form.setFieldsValue({
      ...parsed,
      source:
        editingSkill.kind === "builtin"
          ? t("skills.kindBuiltin")
          : t("skills.kindWorkspace"),
    });
    setLocalEditMode(false);
    setEditorTab("form");
    setViewTab("preview");
  };

  const syncFormToSource = () => {
    const values = form.getFieldsValue();
    form.setFieldValue("content", buildSkillMarkdown(values));
  };

  const handleEditorTabChange = (next: EditorTab) => {
    if (next === editorTab) return;
    if (next === "source") {
      syncFormToSource();
    } else {
      const content = String(form.getFieldValue("content") || "");
      if (!content.trim()) {
        message.warning(t("skills.sourceEmpty"));
        return;
      }
      applySourceToFormFields(form, content);
    }
    setEditorTab(next);
  };

  const handleSubmit = (values: SkillFormValues) => {
    if (!isCreate && !isEdit) return;
    if (editorTab === "source") {
      const content = String(values.content || "").trim();
      if (!content) {
        message.warning(t("skills.sourceEmpty"));
        return;
      }
      const { body } = splitMarkdownFrontmatter(content);
      const fm = splitMarkdownFrontmatter(content).raw ?? "";
      const name = yamlTopLevel(fm, "name") || values.name;
      // Edits keep the existing slug (updateSkill ignores the name), so only
      // creation needs the slug check - legacy skills with odd names stay editable.
      if (isCreate && !isValidSkillName(name)) {
        message.warning(t("skills.namePattern"));
        return;
      }
      onSubmit({
        ...values,
        name,
        description: yamlTopLevel(fm, "description") || values.description,
        body,
        content,
      });
      return;
    }
    onSubmit({
      ...values,
      content: buildSkillMarkdown(values),
    });
  };

  const drawerTitle = isCreate
    ? t("skills.createSkill")
    : localEditMode
    ? t("skills.editSkill")
    : t("skills.viewSkill");

  const nameField = (
    <Form.Item
      name="name"
      label={t("skills.nameLabel")}
      rules={
        isCreate && editorTab === "form"
          ? [
              { required: true, message: t("skills.pleaseInputName") },
              {
                validator: (_: unknown, value: string) => {
                  // Empty is reported by the required rule above.
                  if (!String(value ?? "").trim()) return Promise.resolve();
                  return isValidSkillName(String(value))
                    ? Promise.resolve()
                    : Promise.reject(new Error(t("skills.namePattern")));
                },
              },
            ]
          : undefined
      }
    >
      <Input
        placeholder={t("skills.skillNamePlaceholder")}
        disabled={!isCreate}
      />
    </Form.Item>
  );

  const descriptionField = (
    <Form.Item
      name="description"
      label={t("skills.skillDescription")}
      rules={
        fieldsEditable && editorTab === "form"
          ? [{ required: true, message: t("skills.pleaseInputDescription") }]
          : undefined
      }
    >
      <Input.TextArea
        placeholder={t("skills.descriptionPlaceholder")}
        autoSize={{ minRows: 2, maxRows: fieldsEditable ? 4 : 6 }}
        disabled={!fieldsEditable}
      />
    </Form.Item>
  );

  const emojiField = (
    <Form.Item
      name="emoji"
      label={t("skills.emojiLabel")}
      extra={fieldsEditable ? t("skills.emojiHint") : undefined}
    >
      {fieldsEditable ? (
        <EmojiPicker fallback={DEFAULT_SKILL_EMOJI} />
      ) : (
        <Input disabled />
      )}
    </Form.Item>
  );

  const metadataFields = (
    <div className={styles.metadataBlock}>
      <Form.List name="metadata">
        {(fields, { add, remove }) => (
          <>
            <div className={styles.metadataHeader}>
              <span className={styles.metadataLabel}>
                {t("skills.metadataLabel")}
              </span>
              {fieldsEditable ? (
                <Button
                  type="dashed"
                  size="small"
                  icon={<Plus size={14} />}
                  onClick={() => add({ key: "", value: "" })}
                >
                  {t("skills.addMetadata")}
                </Button>
              ) : null}
            </div>
            {fields.map((field) => (
              <div className={styles.metadataRow} key={field.key}>
                <Form.Item name={[field.name, "key"]}>
                  <Input
                    placeholder={t("skills.metadataKey")}
                    disabled={!fieldsEditable}
                  />
                </Form.Item>
                <Form.Item name={[field.name, "value"]}>
                  <Input
                    placeholder={t("skills.metadataValue")}
                    disabled={!fieldsEditable}
                  />
                </Form.Item>
                {fieldsEditable ? (
                  <Button
                    type="text"
                    danger
                    icon={<MinusCircle size={14} />}
                    onClick={() => remove(field.name)}
                    aria-label={t("common.delete")}
                  />
                ) : (
                  <span />
                )}
              </div>
            ))}
          </>
        )}
      </Form.List>
    </div>
  );

  const bodyEditBlock = (
    <div className={styles.bodyBlock}>
      <div className={styles.bodyLabel}>
        <span className={styles.bodyRequired}>*</span>
        {t("skills.bodyLabel")}
      </div>
      <Form.Item
        name="body"
        noStyle
        rules={
          editorTab === "form"
            ? [{ required: true, message: t("skills.pleaseInputBody") }]
            : undefined
        }
      >
        <textarea
          className={styles.bodyTextarea}
          placeholder={t("skills.bodyPlaceholder")}
        />
      </Form.Item>
    </div>
  );

  const sourceEditBlock = (
    <div className={styles.bodyBlock}>
      <div className={styles.bodyLabel}>
        <span className={styles.bodyRequired}>*</span>
        {t("skills.fullSourceLabel")}
      </div>
      <Form.Item
        name="content"
        noStyle
        rules={
          editorTab === "source"
            ? [{ required: true, message: t("skills.sourceEmpty") }]
            : undefined
        }
      >
        <textarea
          className={styles.bodyTextarea}
          placeholder={t("skills.fullSourcePlaceholder")}
          spellCheck={false}
        />
      </Form.Item>
    </div>
  );

  /** Preview must never dump YAML frontmatter as markdown. */
  const previewMarkdown =
    editingSkill?.body ||
    (editingSkill?.raw ? splitMarkdownFrontmatter(editingSkill.raw).body : "");

  const viewContentBlock = (
    <div className={styles.contentViewBlock}>
      <div className={styles.contentViewHeader}>
        <span className={styles.contentViewLabel}>{t("skills.bodyLabel")}</span>
        <Segmented
          size="small"
          value={viewTab}
          onChange={(value) => setViewTab(value as ViewTab)}
          options={[
            { value: "preview", label: t("skills.viewPreview") },
            { value: "source", label: t("skills.viewSource") },
          ]}
        />
      </div>
      {viewTab === "preview" ? (
        <div className={styles.previewPane}>
          {previewMarkdown ? (
            <Markdown content={previewMarkdown} />
          ) : (
            <span className={styles.emptyContent}>—</span>
          )}
        </div>
      ) : (
        <pre className={styles.sourcePane}>{editingSkill?.raw || "—"}</pre>
      )}
    </div>
  );

  const editorModeToggle = (
    <div className={styles.editorTabs}>
      <Segmented
        size="small"
        value={editorTab}
        onChange={(value) => handleEditorTabChange(value as EditorTab)}
        options={[
          { value: "form", label: t("skills.editorForm") },
          { value: "source", label: t("skills.editorSource") },
        ]}
      />
    </div>
  );

  const siblingFileName =
    selectedFilePath?.split("/").filter(Boolean).pop() ?? "";
  const siblingUsesRichPreview = Boolean(
    selectedFilePath &&
      (getMediaKind(selectedFilePath) || getDocKind(selectedFilePath)),
  );

  const siblingFileBlock = (
    <div className={styles.contentViewBlock}>
      <div className={styles.contentViewHeader}>
        <span className={styles.contentViewLabel}>{siblingFileName}</span>
        {!siblingUsesRichPreview ? (
          <Segmented
            size="small"
            value={siblingViewTab}
            onChange={(value) => setSiblingViewTab(value as ViewTab)}
            options={[
              { value: "preview", label: t("skills.viewPreview") },
              { value: "source", label: t("skills.viewSource") },
            ]}
          />
        ) : null}
      </div>
      {!workspaceReady ? (
        <div className={styles.siblingEmpty}>
          {t("skills.fileTreeAgentNotReady")}
        </div>
      ) : agentId && selectedFilePath ? (
        <div className={styles.siblingViewer}>
          <FileViewer
            agentId={agentId}
            path={selectedFilePath}
            fromWorkspace
            editMode={false}
            value={siblingContent}
            onChange={() => {}}
            fileLoading={siblingLoading}
            previewMode={siblingViewTab === "preview"}
          />
        </div>
      ) : (
        <div className={styles.siblingEmpty}>—</div>
      )}
    </div>
  );

  const mainPanel = (
    <Form
      form={form}
      layout="vertical"
      className={isCreate || isEdit ? styles.createForm : styles.viewForm}
      onFinish={handleSubmit}
    >
      {viewingSkillMd ? (
        isCreate || isEdit ? (
          <div className={styles.createLayout}>
            {editorModeToggle}
            {editorTab === "form" ? (
              <>
                <div className={styles.createFields}>
                  {nameField}
                  {descriptionField}
                  {emojiField}
                  {metadataFields}
                </div>
                {bodyEditBlock}
              </>
            ) : (
              sourceEditBlock
            )}
          </div>
        ) : (
          <div className={styles.viewScroll}>
            {nameField}
            {descriptionField}
            {emojiField}
            <Form.Item name="source" label={t("skills.sourceLabel")}>
              <Input disabled />
            </Form.Item>
            <Form.Item name="path" label={t("skills.pathLabel")}>
              <Input disabled />
            </Form.Item>
            {viewContentBlock}
          </div>
        )
      ) : (
        <div className={styles.viewScroll}>{siblingFileBlock}</div>
      )}
    </Form>
  );

  return (
    <Drawer
      width={
        showFileTree && !fileTreeCollapsed
          ? "min(1060px, 95vw)"
          : "min(860px, 92vw)"
      }
      placement="right"
      title={drawerTitle}
      open={open}
      onClose={onClose}
      destroyOnHidden
      styles={{
        body: {
          padding: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          height: "calc(100vh - 55px)",
        },
      }}
    >
      <div className={styles.shell}>
        <div className={showFileTree ? styles.splitBody : styles.singleBody}>
          {showFileTree && skillRoot && agentId && !fileTreeCollapsed ? (
            <SkillFileTree
              agentId={agentId}
              skillRoot={skillRoot}
              selectedPath={selectedFilePath}
              onSelectPath={handleSelectFilePath}
              onCollapse={toggleFileTreeCollapsed}
              workspaceReady={workspaceReady}
              selectionDisabled={isEdit}
            />
          ) : null}
          <div
            className={`${styles.mainPane} ${
              showFileTree && fileTreeCollapsed
                ? styles.mainPaneTreeCollapsed
                : ""
            }`}
          >
            {showFileTree && fileTreeCollapsed ? (
              <Tooltip title={t("skills.fileTreeShow")}>
                <button
                  type="button"
                  className={styles.fileTreeExpandBtn}
                  onClick={toggleFileTreeCollapsed}
                  aria-label={t("skills.fileTreeShow")}
                >
                  <PanelLeftOpen size={16} strokeWidth={1.8} />
                </button>
              </Tooltip>
            ) : null}
            {mainPanel}
          </div>
        </div>

        <div className={styles.footer}>
          {isCreate ? (
            <>
              <Button onClick={onClose}>{t("common.cancel")}</Button>
              <Button type="primary" onClick={() => form.submit()}>
                {t("common.create")}
              </Button>
            </>
          ) : isEdit ? (
            <>
              <Button onClick={resetToViewForm}>{t("common.cancel")}</Button>
              <Button type="primary" onClick={() => form.submit()}>
                {t("skills.saveSkill")}
              </Button>
            </>
          ) : (
            <>
              <Button onClick={onClose}>{t("common.close")}</Button>
              {editingSkill?.kind === "workspace" && viewingSkillMd ? (
                <Button
                  type="primary"
                  onClick={() => {
                    if (editingSkill) {
                      setSelectedFilePath(skillManifestPath(editingSkill));
                    }
                    setEditorTab("form");
                    setLocalEditMode(true);
                  }}
                >
                  {t("skills.editSkill")}
                </Button>
              ) : null}
            </>
          )}
        </div>
      </div>
    </Drawer>
  );
}
