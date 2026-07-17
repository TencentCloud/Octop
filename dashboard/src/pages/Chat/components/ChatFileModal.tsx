import { useEffect, useState } from "react";
import {
  Modal,
  Button,
  Select,
  message,
  Tooltip,
  Segmented,
} from "antd";
import { Pencil, Save, ArrowDownToLine } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request, requestBlob } from "../../../api/request";
import FileViewer from "../../Agent/Workspace/components/FileViewer";
import { getDocKind } from "../../Agent/Workspace/utils/docKind";
import { isProbablyText } from "../../Agent/Workspace/utils/fileKind";
import { getPreviewKind } from "../../Agent/Workspace/components/FilePreview";
import styles from "../index.module.less";

interface ChatFileModalProps {
  agentId: string;
  open: boolean;
  /** When set, the dialog opens on this path instead of the latest written one. */
  initialPath?: string | null;
  /** All workspace files written by the agent in this thread. */
  filePaths: string[];
  onClose: () => void;
}

/**
 * Document box surfaced from the chat page: opens the agent-generated file
 * directly in the shared ``FileViewer`` (with an edit / save / download
 * toolbar) instead of the full workspace drawer.
 */
export default function ChatFileModal({
  agentId,
  open,
  initialPath,
  filePaths,
  onClose,
}: ChatFileModalProps) {
  const { t } = useTranslation();
  const [selectedPath, setSelectedPath] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [editMode, setEditMode] = useState(false);
  const [previewMode, setPreviewMode] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const resolvedPath =
    selectedPath || initialPath || filePaths[filePaths.length - 1] || "";

  const docKind = resolvedPath ? getDocKind(resolvedPath) : null;
  const previewKind = resolvedPath ? getPreviewKind(resolvedPath) : null;
  const isText = resolvedPath ? isProbablyText(resolvedPath) : false;
  const showEditButton = isText;
  const showPreviewToggle =
    isText && previewKind !== null && !editMode && content !== "";

  useEffect(() => {
    if (!open || !resolvedPath || !agentId) return;
    setEditMode(false);
    setPreviewMode(true);
    setContent("");
    if (!isText) return;
    let cancelled = false;
    setFileLoading(true);
    request<{ content: string }>(
      `/agents/${agentId}/workspace/file?path=${encodeURIComponent(resolvedPath)}`,
    )
      .then((r) => {
        if (!cancelled) setContent(r.content);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          message.error(
            (err instanceof Error ? err.message : String(err)) ||
              t("workspace.readFailed", "读取失败"),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setFileLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, resolvedPath, agentId, isText]);

  const save = async () => {
    if (!resolvedPath) return;
    setSaving(true);
    try {
      await request(
        `/agents/${agentId}/workspace/file?path=${encodeURIComponent(
          resolvedPath,
        )}`,
        { method: "PUT", body: JSON.stringify({ content }) },
      );
      message.success(t("workspace.saved", "已保存"));
      setEditMode(false);
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.saveFailed", "保存失败"),
      );
    } finally {
      setSaving(false);
    }
  };

  const download = async () => {
    if (!resolvedPath) return;
    try {
      const blob = await requestBlob(
        `/agents/${agentId}/workspace/download?path=${encodeURIComponent(
          resolvedPath,
        )}`,
      );
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = resolvedPath.split("/").pop() || "download";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.downloadFailed", "下载失败"),
      );
    }
  };

  const fileName = resolvedPath
    ? resolvedPath.split("/").filter(Boolean).pop() || resolvedPath
    : "";

  const bodyFill = editMode || docKind !== null;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width="min(960px, 92vw)"
      styles={{
        body: {
          padding: 0,
          display: "flex",
          flexDirection: "column",
          height: "78vh",
        },
      }}
      title={fileName || t("chat.fileWorkspace", "工作区文件")}
      destroyOnClose
    >
      <div className={styles.fileModalToolbar}>
        <div className={styles.fileModalToolbarLeft}>
          {filePaths.length > 1 && (
            <Select
              size="small"
              value={resolvedPath}
              onChange={setSelectedPath}
              className={styles.fileModalSelect}
              aria-label={t("chat.fileSwitch", "切换文件")}
              options={filePaths.map((p) => ({
                value: p,
                label: p.split("/").filter(Boolean).pop() || p,
              }))}
            />
          )}
        </div>
        <div className={styles.fileModalActions}>
          {showPreviewToggle && (
            <Segmented
              size="small"
              value={previewMode ? "preview" : "source"}
              options={[
                { label: t("common.preview"), value: "preview" },
                { label: t("workspace.source", "源码"), value: "source" },
              ]}
              onChange={(v) => setPreviewMode(v === "preview")}
            />
          )}
          <Tooltip title={t("common.download")}>
            <button
              type="button"
              className={styles.fileModalIconBtn}
              onClick={() => void download()}
              aria-label={t("common.download")}
            >
              <ArrowDownToLine size={16} strokeWidth={2} />
            </button>
          </Tooltip>
          {showEditButton &&
            (editMode ? (
              <Button
                size="small"
                type="primary"
                icon={<Save size={14} />}
                loading={saving}
                onClick={() => void save()}
              >
                {t("common.save")}
              </Button>
            ) : (
              <Button
                size="small"
                icon={<Pencil size={14} />}
                onClick={() => setEditMode(true)}
              >
                {t("common.edit")}
              </Button>
            ))}
        </div>
      </div>
      <div
        className={`${styles.fileModalBody} ${
          bodyFill ? styles.fileModalBodyFill : ""
        }`}
      >
        {resolvedPath && (
          <FileViewer
            agentId={agentId}
            path={resolvedPath}
            editMode={editMode}
            value={content}
            onChange={setContent}
            fileLoading={fileLoading}
            previewMode={previewMode}
          />
        )}
      </div>
    </Modal>
  );
}
