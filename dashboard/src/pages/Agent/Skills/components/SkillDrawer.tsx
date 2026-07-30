import { useEffect, useState } from "react";
import { Drawer, Form, Input, Button, Segmented, message } from "antd";
import { MinusCircle, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FormInstance } from "antd";
import Markdown from "../../../../components/Markdown/LazyMarkdown";
import { splitMarkdownFrontmatter } from "../../../../utils/markdown";
import type { SkillDetail } from "../useSkills";
import styles from "./SkillDrawer.module.less";

export interface MetadataEntry {
  key: string;
  value: string;
}

/** Form fields for creating or viewing a skill. */
export interface SkillFormValues {
  name: string;
  description: string;
  metadata: MetadataEntry[];
  body: string;
  content?: string;
  source?: string;
  path?: string;
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
  const meta = buildMetadataObject(values.metadata);
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
  const metadata = flattenMetadata(fm.metadata);
  return {
    name: displayName,
    description,
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

interface SkillDrawerProps {
  open: boolean;
  editingSkill: SkillDetail | null;
  form: FormInstance<SkillFormValues>;
  onClose: () => void;
  onSubmit: (values: SkillFormValues) => void;
}

export function SkillDrawer({
  open,
  editingSkill,
  form,
  onClose,
  onSubmit,
}: SkillDrawerProps) {
  const { t } = useTranslation();
  const isCreate = !editingSkill;
  const [localEditMode, setLocalEditMode] = useState(false);
  const [viewTab, setViewTab] = useState<ViewTab>("preview");
  const [editorTab, setEditorTab] = useState<EditorTab>("form");

  const isEdit = !!editingSkill && localEditMode;
  const fieldsEditable = isCreate || isEdit;

  useEffect(() => {
    if (!open) {
      setLocalEditMode(false);
      setViewTab("preview");
      setEditorTab("form");
      return;
    }
    setLocalEditMode(false);
    setViewTab("preview");
    setEditorTab("form");
    if (editingSkill) {
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
    form.setFieldsValue({
      name: "",
      description: "",
      metadata: [{ key: "octop.emoji", value: "✨" }],
      body: t("skills.newSkillBodyTemplate"),
      content: "",
    });
  }, [editingSkill, form, open, t]);

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
      onSubmit({
        ...values,
        name: yamlTopLevel(fm, "name") || values.name,
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
                pattern: /^[a-zA-Z0-9._-]+$/,
                message: t("skills.namePattern"),
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

  return (
    <Drawer
      width="min(860px, 92vw)"
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
        <Form
          form={form}
          layout="vertical"
          className={
            isCreate || isEdit ? styles.createForm : styles.viewForm
          }
          onFinish={handleSubmit}
        >
          {isCreate || isEdit ? (
            <div className={styles.createLayout}>
              {editorModeToggle}
              {editorTab === "form" ? (
                <>
                  <div className={styles.createFields}>
                    {nameField}
                    {descriptionField}
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
              <Form.Item name="source" label={t("skills.sourceLabel")}>
                <Input disabled />
              </Form.Item>
              <Form.Item name="path" label={t("skills.pathLabel")}>
                <Input disabled />
              </Form.Item>
              {viewContentBlock}
            </div>
          )}
        </Form>

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
              {editingSkill?.kind === "workspace" ? (
                <Button
                  type="primary"
                  onClick={() => {
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
