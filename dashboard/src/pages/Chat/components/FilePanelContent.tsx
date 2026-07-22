import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Select, message, Tooltip, Segmented } from "antd";
import { Pencil, Save, ArrowDownToLine, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request, requestBlob } from "../../../api/request";
import FileViewer from "../../Agent/Workspace/components/FileViewer";
import { getDocKind } from "../../Agent/Workspace/utils/docKind";
import { isProbablyText } from "../../Agent/Workspace/utils/fileKind";
import {
  getPreviewKind,
  previewNeedsFillLayout,
  defaultPreviewMode,
} from "../../Agent/Workspace/components/FilePreview";
import styles from "../index.module.less";

/** Keep tool path shape: absolute stays absolute, relative stays relative. */
function panelFilePath(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.toLowerCase().startsWith("file://")) {
    let abs = trimmed.slice("file://".length);
    if (abs.startsWith("//")) abs = abs.slice(1);
    return abs.startsWith("/") || /^[A-Za-z]:/.test(abs) ? abs : `/${abs}`;
  }
  return trimmed;
}

/** Legacy ``/outbound|inbound/…`` keys are workspace-relative, not host roots. */
function isLegacyWorkspaceSlashPath(path: string): boolean {
  const raw = path.replace(/\\/g, "/");
  return (
    raw.startsWith("/outbound/") ||
    raw.startsWith("/inbound/") ||
    raw === "/outbound" ||
    raw === "/inbound"
  );
}

/** Path + query for agent workspace file/download APIs. */
function panelApiRequestPath(resolvedPath: string): string {
  const raw = resolvedPath.trim();
  if (!raw) return raw;
  if (raw.toLowerCase().startsWith("file://")) {
    return raw;
  }
  if (isLegacyWorkspaceSlashPath(raw)) {
    return raw.replace(/\\/g, "/").replace(/^\//, "");
  }
  if (raw.startsWith("/") || /^[A-Za-z]:/.test(raw)) {
    return raw.startsWith("/") ? `file://${raw}` : `file:///${raw}`;
  }
  return raw;
}

interface FilePanelContentProps {
  agentId: string;
  /** All workspace files written by the agent in this thread. */
  filePaths: string[];
  /** When set, opens on this path instead of the latest written one. */
  initialPath?: string | null;
}

/**
 * Shared file viewer/editor body used by the docked ``FilePanel`` (write/edit
 * tool results and preview/download cards). Paths are passed through as the
 * tool reported them — no collapsing absolute → relative.
 */
export default function FilePanelContent({
  agentId,
  filePaths,
  initialPath,
}: FilePanelContentProps) {
  const { t } = useTranslation();
  const normalizedPaths = useMemo(
    () => filePaths.map((p) => panelFilePath(p)),
    [filePaths],
  );
  const normalizedInitial = initialPath ? panelFilePath(initialPath) : null;
  const [selectedPath, setSelectedPath] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [editMode, setEditMode] = useState(false);
  const [previewMode, setPreviewMode] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  // Preview/download cards pass a fresh initialPath; sync selection to it.
  useEffect(() => {
    if (normalizedInitial) {
      setSelectedPath(normalizedInitial);
    }
  }, [normalizedInitial]);

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

  const apiFilePath = useMemo(
    () => panelApiRequestPath(resolvedPath),
    [resolvedPath],
  );

  useEffect(() => {
    if (!resolvedPath || !agentId) return;
    setEditMode(false);
    setPreviewMode(defaultPreviewMode(resolvedPath));
    setContent("");
    if (!isText) return;
    let cancelled = false;
    setFileLoading(true);
    request<{ content: string }>(
      `/agents/${agentId}/workspace/file?path=${encodeURIComponent(
        apiFilePath,
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
  }, [resolvedPath, apiFilePath, agentId, isText, refreshToken]);

  const refresh = useCallback(() => {
    setEditMode(false);
    setRefreshToken((n) => n + 1);
  }, []);

  const save = async () => {
    if (!resolvedPath) return;
    setSaving(true);
    try {
      await request(
        `/agents/${agentId}/workspace/file?path=${encodeURIComponent(
          apiFilePath,
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
          apiFilePath,
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
    <div className={styles.filePanelBody}>
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
          <Tooltip title={t("common.refresh")}>
            <button
              type="button"
              className={styles.fileModalIconBtn}
              onClick={refresh}
              disabled={!resolvedPath || fileLoading}
              aria-label={t("common.refresh")}
            >
              <RefreshCw size={16} strokeWidth={2} />
            </button>
          </Tooltip>
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
            refreshToken={refreshToken}
          />
        )}
      </div>
    </div>
  );
}
