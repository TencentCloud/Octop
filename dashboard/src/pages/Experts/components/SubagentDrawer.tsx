import { useEffect, useState } from "react";
import { Button, Drawer, Form, Input, Segmented, Spin } from "antd";
import { message } from "@/utils/antdMessage";
import type { FormInstance } from "antd";
import { useTranslation } from "react-i18next";
import ExpertColorPicker from "../../../components/ExpertColorPicker";
import EmojiPicker from "../../../components/EmojiPicker";
import {
  expertPaletteColor,
  resolveExpertPalette,
} from "../../../utils/expertColor";
import { splitMarkdownFrontmatter } from "../../../utils/markdown";
import { DEFAULT_PALETTE } from "../../../styles/themePalettes";
import styles from "./SubagentDrawer.module.less";

export interface SubagentFormValues {
  slug: string;
  name: string;
  description: string;
  emoji: string;
  color: string;
  body: string;
  content?: string;
}

export interface EditingSubagent {
  slug: string;
  path: string;
  content: string;
}

type EditorTab = "form" | "source";

export const SUBAGENT_SLUG_PATTERN = /^[a-z0-9][a-z0-9_-]*$/;

/** Form-bound adapter: stores hex in the form, shows curated swatches. */
function SubagentColorField({
  value,
  onChange,
}: {
  value?: string;
  onChange?: (hex: string) => void;
}) {
  return (
    <ExpertColorPicker
      value={resolveExpertPalette(value)}
      onChange={(palette) => onChange?.(expertPaletteColor(palette))}
    />
  );
}

function yamlQuote(value: string): string {
  if (!value) return '""';
  if (/[:#\n"'{}[\],&*?|>!%@`]/.test(value) || value.trim() !== value) {
    return JSON.stringify(value);
  }
  return value;
}

function yamlTopLevel(block: string, key: string): string {
  const re = new RegExp(`^${key}:\\s*(.+?)\\s*$`, "m");
  const match = block.match(re);
  if (!match) return "";
  return (match[1] || "").trim().replace(/^["']|["']$/g, "");
}

export function buildSubagentMarkdown(values: SubagentFormValues): string {
  const lines = [
    "---",
    `name: ${yamlQuote(values.name.trim())}`,
    `description: ${yamlQuote(values.description.trim())}`,
  ];
  const emoji = values.emoji.trim();
  if (emoji) lines.push(`emoji: ${yamlQuote(emoji)}`);
  const color = values.color.trim();
  if (color) lines.push(`color: ${yamlQuote(color)}`);
  lines.push("---");
  const body = values.body.trim();
  return body ? `${lines.join("\n")}\n\n${body}\n` : `${lines.join("\n")}\n`;
}

export function parseSubagentForm(
  content: string,
  slugFallback = "",
): SubagentFormValues {
  const { raw, body } = splitMarkdownFrontmatter(content);
  const fm = raw ?? "";
  return {
    slug: slugFallback,
    name: yamlTopLevel(fm, "name") || slugFallback,
    description: yamlTopLevel(fm, "description"),
    emoji: yamlTopLevel(fm, "emoji") || "🤖",
    color: yamlTopLevel(fm, "color"),
    body,
    content,
  };
}

function applySourceToFormFields(
  form: FormInstance<SubagentFormValues>,
  content: string,
): void {
  const parsed = parseSubagentForm(
    content,
    String(form.getFieldValue("slug") || ""),
  );
  form.setFieldsValue({
    ...parsed,
    content,
  });
}

interface SubagentDrawerProps {
  open: boolean;
  editing: EditingSubagent | null;
  loading?: boolean;
  saving?: boolean;
  form: FormInstance<SubagentFormValues>;
  onClose: () => void;
  onSubmit: (values: SubagentFormValues) => void | Promise<void>;
}

export function SubagentDrawer({
  open,
  editing,
  loading = false,
  saving = false,
  form,
  onClose,
  onSubmit,
}: SubagentDrawerProps) {
  const { t } = useTranslation();
  const isCreate = !editing;
  const [editorTab, setEditorTab] = useState<EditorTab>("form");

  useEffect(() => {
    if (!open) {
      setEditorTab("form");
      return;
    }
    setEditorTab("form");
    if (editing) {
      form.setFieldsValue(parseSubagentForm(editing.content, editing.slug));
      return;
    }
    form.setFieldsValue({
      slug: "",
      name: "",
      description: "",
      emoji: "🤖",
      color: expertPaletteColor(DEFAULT_PALETTE),
      body: t("subagents.newBodyTemplate"),
      content: "",
    });
  }, [editing, form, open, t]);

  const syncFormToSource = () => {
    const values = form.getFieldsValue();
    form.setFieldValue("content", buildSubagentMarkdown(values));
  };

  const handleEditorTabChange = (next: EditorTab) => {
    if (next === editorTab) return;
    if (next === "source") {
      syncFormToSource();
    } else {
      const content = String(form.getFieldValue("content") || "");
      if (!content.trim()) {
        message.warning(t("subagents.sourceEmpty"));
        return;
      }
      applySourceToFormFields(form, content);
    }
    setEditorTab(next);
  };

  const handleSubmit = (values: SubagentFormValues) => {
    if (editorTab === "source") {
      const content = String(values.content || "").trim();
      if (!content) {
        message.warning(t("subagents.sourceEmpty"));
        return;
      }
      const { body } = splitMarkdownFrontmatter(content);
      const fm = splitMarkdownFrontmatter(content).raw ?? "";
      void onSubmit({
        ...values,
        name: yamlTopLevel(fm, "name") || values.name,
        description: yamlTopLevel(fm, "description") || values.description,
        emoji: yamlTopLevel(fm, "emoji") || values.emoji,
        color: yamlTopLevel(fm, "color") || values.color,
        body,
        content,
      });
      return;
    }
    void onSubmit({
      ...values,
      content: buildSubagentMarkdown(values),
    });
  };

  const drawerTitle = isCreate
    ? t("subagents.createSubagent")
    : t("subagents.editSubagent");

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
        {loading ? (
          <div className={styles.loadingWrap}>
            <Spin />
          </div>
        ) : (
          <Form
            form={form}
            layout="vertical"
            className={styles.createForm}
            onFinish={handleSubmit}
          >
            <div className={styles.createLayout}>
              <div className={styles.editorTabs}>
                <Segmented
                  size="small"
                  value={editorTab}
                  onChange={(value) =>
                    handleEditorTabChange(value as EditorTab)
                  }
                  options={[
                    { value: "form", label: t("subagents.editorForm") },
                    { value: "source", label: t("subagents.editorSource") },
                  ]}
                />
              </div>

              {editorTab === "form" ? (
                <>
                  <div className={styles.createFields}>
                    <Form.Item
                      name="slug"
                      label={t("subagents.slugLabel")}
                      extra={isCreate ? t("subagents.slugHint") : undefined}
                      rules={
                        isCreate
                          ? [
                              {
                                required: true,
                                message: t("subagents.pleaseInputSlug"),
                              },
                              {
                                pattern: SUBAGENT_SLUG_PATTERN,
                                message: t("subagents.slugPattern"),
                              },
                            ]
                          : undefined
                      }
                    >
                      <Input
                        placeholder={t("subagents.slugPlaceholder")}
                        disabled={!isCreate}
                      />
                    </Form.Item>
                    <Form.Item
                      name="name"
                      label={t("subagents.nameLabel")}
                      rules={[
                        {
                          required: true,
                          message: t("subagents.pleaseInputName"),
                        },
                      ]}
                    >
                      <Input placeholder={t("subagents.namePlaceholder")} />
                    </Form.Item>
                    <Form.Item
                      name="description"
                      label={t("subagents.descriptionLabel")}
                      rules={[
                        {
                          required: true,
                          message: t("subagents.pleaseInputDescription"),
                        },
                      ]}
                    >
                      <Input.TextArea
                        placeholder={t("subagents.descriptionPlaceholder")}
                        autoSize={{ minRows: 2, maxRows: 4 }}
                      />
                    </Form.Item>
                    <Form.Item
                      name="emoji"
                      label={t("subagents.emojiLabel")}
                      extra={t("subagents.emojiHint")}
                    >
                      <EmojiPicker />
                    </Form.Item>
                    <Form.Item
                      name="color"
                      label={t("subagents.colorLabel")}
                      extra={t("subagents.colorHint")}
                    >
                      <SubagentColorField />
                    </Form.Item>
                  </div>
                  <div className={styles.bodyBlock}>
                    <div className={styles.bodyLabel}>
                      <span className={styles.bodyRequired}>*</span>
                      {t("subagents.bodyLabel")}
                    </div>
                    <Form.Item
                      name="body"
                      noStyle
                      rules={[
                        {
                          required: true,
                          message: t("subagents.pleaseInputBody"),
                        },
                      ]}
                    >
                      <textarea
                        className={styles.bodyTextarea}
                        placeholder={t("subagents.bodyPlaceholder")}
                      />
                    </Form.Item>
                  </div>
                </>
              ) : (
                <div className={styles.bodyBlock}>
                  <div className={styles.bodyLabel}>
                    <span className={styles.bodyRequired}>*</span>
                    {t("subagents.fullSourceLabel")}
                  </div>
                  <Form.Item
                    name="content"
                    noStyle
                    rules={[
                      {
                        required: true,
                        message: t("subagents.sourceEmpty"),
                      },
                    ]}
                  >
                    <textarea
                      className={styles.bodyTextarea}
                      placeholder={t("subagents.fullSourcePlaceholder")}
                      spellCheck={false}
                    />
                  </Form.Item>
                </div>
              )}
            </div>
          </Form>
        )}

        <div className={styles.footer}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            type="primary"
            loading={saving}
            disabled={loading}
            onClick={() => form.submit()}
          >
            {isCreate ? t("common.create") : t("common.save")}
          </Button>
        </div>
      </div>
    </Drawer>
  );
}
