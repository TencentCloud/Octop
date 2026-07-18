import { useEffect, useMemo, useState } from "react";
import { Button, Select, message, Tooltip, Segmented } from "antd";
import { Pencil, Save, ArrowDownToLine } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request, requestBlob } from "../../../api/request";
import FileViewer from "../../Agent/Workspace/components/FileViewer";
import { getDocKind } from "../../Agent/Workspace/utils/docKind";
import { isProbablyText } from "../../Agent/Workspace/utils/fileKind";
import {
  getPreviewKind,
  previewNeedsFillLayout,
} from "../../Agent/Workspace/components/FilePreview";
import { toWorkspaceRelativePath } from "../../../utils/workspacePath";
import styles from "../index.module.less";

interface FilePanelContentProps {
  agentId: string;
  /** All workspace files written by the agent in this thread. */
  filePaths: string[];
  /** When set, opens on this path instead of the latest written one. */
  initialPath?: string | null;
}

/**
 * Shared file viewer/editor body used by both the centered ``ChatFileModal``
 * (auth download previews) and the docked ``FilePanel`` (write/edit tool
 * results). Tools may report an absolute on-disk path, which is collapsed to
 * the workspace-relative fragment the file API expects.
 */
export default function FilePanelContent({
  agentId,
  filePaths,
  initialPath,
}: FilePanelContentProps) {
  const { t } = useTranslation();
  const normalizedPaths = useMemo(
    () => filePaths.map((p) => toWorkspaceRelativePath(p, agentId)),
    [filePaths, agentId],
  );
  const normalizedInitial = initialPath
    ? toWorkspaceRelativePath(initialPath, agentId)
    : null;
  const [selectedPath, setSelectedPath] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [editMode, setEditMode] = useState(false);
  const [previewMode, setPreviewMode] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const resolvedPath =
    selectedPath ||
    normalizedInitial ||
    normalizedPaths[normalizedPaths.length - 1] ||
    "";

  const docKind = resolvedPath ? getDocKind(resolvedPath) : null;
  const previewKind = resolvedPath ? getPreviewKind(resolvedPath) : null;
  const isText = resolvedPath ? isProbablyText(resolvedPath) : false;
  const showEditButton = isText;
  const showPreviewToggle =
    isText && previewKind !== null && !editMode && content !== "";

  useEffect(() => {
    if (!resolvedPath || !agentId) return;
    setEditMode(false);
    setPreviewMode(true);
    setContent("");
    if (!isText) return;
    let cancelled = false;
    setFileLoading(true);
    request<{ content: string }>(
      `/agents/${agentId}/workspace/file?path=${encodeURIComponent(
        resolvedPath,
      )}`,
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
  }, [resolvedPath, agentId, isText]);

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

  const bodyFill =
    editMode ||
    docKind !== null ||
    (previewMode && previewNeedsFillLayout(previewKind));

  return (
    <>
      <div className={styles.fileModalToolbar}>
        <div className={styles.fileModalToolbarLeft}>
          {normalizedPaths.length > 1 && (
            <Select
              size="small"
              value={resolvedPath}
              onChange={setSelectedPath}
              className={styles.fileModalSelect}
              aria-label={t("chat.fileSwitch", "切换文件")}
              options={normalizedPaths.map((p) => ({
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
    </>
  );
}
