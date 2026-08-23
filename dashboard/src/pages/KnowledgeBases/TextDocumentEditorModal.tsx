import { useEffect, useState } from "react";
import { Button, Drawer, Form, Input, Segmented, Select, Spin } from "antd";
import { Eye, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

import Markdown from "../../components/Markdown";
import styles from "./index.module.less";

export type TextDocumentFormat = "md" | "txt";

export type TextDocumentEditorMode = "create" | "edit";

type MdViewMode = "edit" | "preview";

export interface TextDocumentEditorValues {
  name: string;
  format: TextDocumentFormat;
  content: string;
}

interface TextDocumentEditorModalProps {
  open: boolean;
  mode: TextDocumentEditorMode;
  loading?: boolean;
  saving?: boolean;
  initialName?: string;
  initialFormat?: TextDocumentFormat;
  initialContent?: string;
  onCancel: () => void;
  onSubmit: (values: TextDocumentEditorValues) => void | Promise<void>;
}

export function isEditableKnowledgeDocument(doc: {
  is_dir?: boolean;
  content_type?: string;
  filename?: string;
}): boolean {
  if (doc.is_dir) return false;
  const ct = (doc.content_type || "").toLowerCase();
  if (ct === "text/plain" || ct === "text/markdown") return true;
  const name = (doc.filename || "").toLowerCase();
  return name.endsWith(".md") || name.endsWith(".txt");
}

export default function TextDocumentEditorModal({
  open,
  mode,
  loading = false,
  saving = false,
  initialName = "",
  initialFormat = "md",
  initialContent = "",
  onCancel,
  onSubmit,
}: TextDocumentEditorModalProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<TextDocumentEditorValues>();
  const format = Form.useWatch("format", form) ?? initialFormat;
  const content = Form.useWatch("content", form) ?? "";
  const [mdView, setMdView] = useState<MdViewMode>("edit");

  useEffect(() => {
    if (!open) return;
    setMdView("edit");
    form.setFieldsValue({
      name: initialName,
      format: initialFormat,
      content: initialContent,
    });
  }, [open, initialName, initialFormat, initialContent, form]);

  useEffect(() => {
    if (format !== "md") setMdView("edit");
  }, [format]);

  const [submitting, setSubmitting] = useState(false);
  const busy = saving || submitting;

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await onSubmit({
        name: values.name.trim(),
        format: values.format,
        content: values.content ?? "",
      });
    } catch {
      // validation errors stay in the form
    } finally {
      setSubmitting(false);
    }
  };

  const drawerWidth = Math.min(
    880,
    typeof window !== "undefined" ? window.innerWidth - 16 : 880,
  );

  const title =
    mode === "create"
      ? t("knowledgeBases.createFile")
      : t("knowledgeBases.editDocument");

  return (
    <Drawer
      open={open}
      placement="right"
      title={
        <div className={styles.textEditorTitle}>
          <span className={styles.textEditorTitleMain}>{title}</span>
          {mode === "edit" && initialName ? (
            <span className={styles.textEditorTitleSub} title={initialName}>
              {initialName}
            </span>
          ) : null}
        </div>
      }
      onClose={onCancel}
      destroyOnClose
      width={drawerWidth}
      className={styles.textEditorDrawer}
      styles={{
        body: { padding: 0, display: "flex", overflow: "hidden" },
        footer: { padding: "12px 20px" },
      }}
      footer={
        <div className={styles.textEditorFooter}>
          <Button onClick={onCancel} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button
            type="primary"
            loading={busy}
            disabled={loading}
            onClick={() => void handleOk()}
          >
            {t("common.save")}
          </Button>
        </div>
      }
    >
      {loading ? (
        <div className={styles.textEditorLoading}>
          <Spin />
        </div>
      ) : (
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          className={styles.textEditorForm}
          initialValues={{
            name: initialName,
            format: initialFormat,
            content: initialContent,
          }}
        >
          {mode === "create" ? (
            <div className={styles.textEditorMeta}>
              <Form.Item
                name="name"
                label={t("knowledgeBases.filename")}
                rules={[
                  {
                    required: true,
                    message: t("knowledgeBases.filenameRequired"),
                  },
                ]}
                className={styles.textEditorNameItem}
              >
                <Input
                  size="large"
                  placeholder={t("knowledgeBases.filenamePlaceholder")}
                />
              </Form.Item>
              <Form.Item
                name="format"
                label={t("knowledgeBases.fileFormat")}
                rules={[{ required: true }]}
                className={styles.textEditorFormatItem}
              >
                <Select
                  size="large"
                  options={[
                    { value: "md", label: "Markdown (.md)" },
                    { value: "txt", label: "Text (.txt)" },
                  ]}
                />
              </Form.Item>
            </div>
          ) : null}

          <div className={styles.textEditorWorkspace}>
            <div className={styles.textEditorToolbar}>
              <span className={styles.textEditorToolbarLabel}>
                {t("knowledgeBases.fileContent")}
              </span>
              {format === "md" ? (
                <Segmented
                  size="small"
                  value={mdView}
                  onChange={(value) => setMdView(value as MdViewMode)}
                  options={[
                    {
                      value: "edit",
                      icon: <Pencil size={12} />,
                      label: t("common.edit"),
                    },
                    {
                      value: "preview",
                      icon: <Eye size={12} />,
                      label: t("common.preview"),
                    },
                  ]}
                />
              ) : null}
            </div>

            <div className={styles.textEditorStage}>
              <div
                className={styles.textEditorPane}
                hidden={format === "md" && mdView === "preview"}
              >
                <Form.Item name="content" noStyle>
                  <Input.TextArea
                    className={styles.txtEditor}
                    placeholder={t("knowledgeBases.fileContentPlaceholder")}
                  />
                </Form.Item>
              </div>
              {format === "md" && mdView === "preview" ? (
                <div className={styles.mdPreviewPane}>
                  {content.trim() ? (
                    <Markdown content={content} />
                  ) : (
                    <span className={styles.mdPreviewEmpty}>
                      {t("knowledgeBases.previewEmpty")}
                    </span>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </Form>
      )}
    </Drawer>
  );
}
