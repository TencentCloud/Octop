import { useEffect } from "react";
import { Drawer, Form, Input, Button, message } from "antd";
import { MinusCircle, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FormInstance } from "antd";
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

  useEffect(() => {
    if (!open) return;
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
    });
  }, [editingSkill, form, open, t]);

  const handleSubmit = (values: SkillFormValues) => {
    if (editingSkill) {
      message.warning(t("skills.editNotSupported"));
      onClose();
      return;
    }
    onSubmit({
      ...values,
      content: buildSkillMarkdown(values),
    });
  };

  const nameField = (
    <Form.Item
      name="name"
      label={t("skills.nameLabel")}
      rules={
        isCreate
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
        isCreate
          ? [{ required: true, message: t("skills.pleaseInputDescription") }]
          : undefined
      }
    >
      <Input.TextArea
        placeholder={t("skills.descriptionPlaceholder")}
        autoSize={{ minRows: 2, maxRows: isCreate ? 4 : 6 }}
        disabled={!isCreate}
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
              {isCreate ? (
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
                    disabled={!isCreate}
                  />
                </Form.Item>
                <Form.Item name={[field.name, "value"]}>
                  <Input
                    placeholder={t("skills.metadataValue")}
                    disabled={!isCreate}
                  />
                </Form.Item>
                {isCreate ? (
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

  return (
    <Drawer
      width="min(860px, 92vw)"
      placement="right"
      title={isCreate ? t("skills.createSkill") : t("skills.viewSkill")}
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
          className={isCreate ? styles.createForm : styles.viewForm}
          onFinish={handleSubmit}
        >
          {isCreate ? (
            <div className={styles.createLayout}>
              <div className={styles.createFields}>
                {nameField}
                {descriptionField}
                {metadataFields}
              </div>
              <div className={styles.bodyBlock}>
                <div className={styles.bodyLabel}>
                  <span className={styles.bodyRequired}>*</span>
                  {t("skills.bodyLabel")}
                </div>
                <Form.Item
                  name="body"
                  noStyle
                  rules={[
                    { required: true, message: t("skills.pleaseInputBody") },
                  ]}
                >
                  <textarea
                    className={styles.bodyTextarea}
                    placeholder={t("skills.bodyPlaceholder")}
                  />
                </Form.Item>
              </div>
            </div>
          ) : (
            <div className={styles.viewScroll}>
              {nameField}
              {descriptionField}
              {metadataFields}
              <Form.Item name="source" label={t("skills.sourceLabel")}>
                <Input disabled />
              </Form.Item>
              <Form.Item name="path" label={t("skills.pathLabel")}>
                <Input disabled />
              </Form.Item>
              <Form.Item label={t("skills.bodyLabel")}>
                <div className={styles.viewBody}>
                  {editingSkill?.body || "—"}
                </div>
              </Form.Item>
              <div className={styles.viewNote}>
                <p>{t("skills.editNote")}</p>
              </div>
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
          ) : (
            <Button onClick={onClose}>{t("common.close")}</Button>
          )}
        </div>
      </div>
    </Drawer>
  );
}
