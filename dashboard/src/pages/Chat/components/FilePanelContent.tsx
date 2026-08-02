import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Tooltip } from "antd";
import { message } from "@/utils/antdMessage";

import {
  Pencil,
  Save,
  ArrowDownToLine,
  RefreshCw,
  FileX,
  Eye,
  Code2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { probeAuthResource, request, requestBlob } from "../../../api/request";
import { isNotFoundApiError } from "../../../utils/apiError";
import FileViewer from "../../Agent/Workspace/components/FileViewer";
import { getDocKind } from "../../Agent/Workspace/utils/docKind";
import { isProbablyText } from "../../Agent/Workspace/utils/fileKind";
import { getMediaKind } from "../../Agent/Workspace/utils/mediaKind";
import {
  getPreviewKind,
  previewNeedsFillLayout,
  defaultPreviewMode,
} from "../../Agent/Workspace/components/FilePreview";
import {
  dockFileBasename,
  normalizeDockFilePath,
  toWorkspaceApiPath,
} from "../utils/dockFilePath";
import styles from "../index.module.less";

interface FilePanelContentProps {
  agentId: string;
  /** Single workspace file path for this tab. */
  filePath: string;
  /** Lift toolbar actions into the shared dock shell (active tab only). */
  onActionsChange?: (actions: ReactNode | null) => void;
}

/**
 * Shared file viewer/editor body used by a dock file tab (write/edit/send
 * tool results and preview/download cards).
 */
export default function FilePanelContent({
  agentId,
  filePath,
  onActionsChange,
}: FilePanelContentProps) {
  const { t } = useTranslation();
  const resolvedPath = normalizeDockFilePath(filePath);
  const [content, setContent] = useState<string>("");
  const [editMode, setEditMode] = useState(false);
  const [previewMode, setPreviewMode] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileMissing, setFileMissing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  const docKind = resolvedPath ? getDocKind(resolvedPath) : null;
  const mediaKind = resolvedPath ? getMediaKind(resolvedPath) : null;
  const previewKind = resolvedPath ? getPreviewKind(resolvedPath) : null;
  const isText = resolvedPath ? isProbablyText(resolvedPath) : false;
  const showEditButton = isText && !fileMissing;
  const showPreviewToggle =
    isText &&
    previewKind !== null &&
    !editMode &&
    content !== "" &&
    !fileMissing;

  const apiFilePath = useMemo(
    () => toWorkspaceApiPath(resolvedPath),
    [resolvedPath],
  );

  useEffect(() => {
    if (!resolvedPath || !agentId) return;
    setEditMode(false);
    setPreviewMode(defaultPreviewMode(resolvedPath));
    setContent("");
    setFileMissing(false);

    let cancelled = false;
    setFileLoading(true);

    const finishOk = () => {
      if (!cancelled) {
        setFileMissing(false);
        setFileLoading(false);
      }
    };
    const finishError = (err: unknown) => {
      if (cancelled) return;
      setFileLoading(false);
      if (isNotFoundApiError(err)) {
        setFileMissing(true);
        return;
      }
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.readFailed", "读取失败"),
      );
    };

    // Text: load content. Unknown/binary: light existence probe (no body buffer).
    // Media/doc: viewers fetch themselves and surface 404 locally.
    if (isText) {
      request<{ content: string }>(
        `/agents/${agentId}/workspace/file?path=${encodeURIComponent(
          apiFilePath,
        )}`,
      )
        .then((r) => {
          if (!cancelled) {
            setContent(r.content);
            finishOk();
          }
        })
        .catch(finishError);
    } else if (mediaKind || docKind) {
      finishOk();
    } else {
      probeAuthResource(
        `/agents/${agentId}/workspace/download?path=${encodeURIComponent(
          apiFilePath,
        )}`,
      )
        .then(() => finishOk())
        .catch(finishError);
    }

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    resolvedPath,
    apiFilePath,
    agentId,
    isText,
    mediaKind,
    docKind,
    refreshToken,
  ]);

  const refresh = useCallback(() => {
    setEditMode(false);
    setRefreshToken((n) => n + 1);
  }, []);

  const save = useCallback(async () => {
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
  }, [agentId, apiFilePath, content, resolvedPath, t]);

  const download = useCallback(async () => {
    if (!resolvedPath) return;
    try {
      const blob = await requestBlob(
        `/agents/${agentId}/workspace/download?path=${encodeURIComponent(
          apiFilePath,
        )}`,
      );
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = dockFileBasename(resolvedPath) || "download";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err: unknown) {
      if (isNotFoundApiError(err)) {
        setFileMissing(true);
        message.warning(t("workspace.fileMaybeDeleted", "文件可能已被删除"));
        return;
      }
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.downloadFailed", "下载失败"),
      );
    }
  }, [agentId, apiFilePath, resolvedPath, t]);

  const bodyFill =
    !fileMissing &&
    (editMode ||
      docKind !== null ||
      (previewMode && previewNeedsFillLayout(previewKind)));

  useLayoutEffect(() => {
    if (!onActionsChange) return;

    const actions = (
      <>
        {showPreviewToggle && (
          <Tooltip
            title={
              previewMode ? t("workspace.source", "源码") : t("common.preview")
            }
          >
            <button
              type="button"
              className={`${styles.fileModalIconBtn} ${
                previewMode ? styles.fileModalIconBtnActive : ""
              }`}
              onClick={() => setPreviewMode((v) => !v)}
              aria-label={
                previewMode
                  ? t("workspace.source", "源码")
                  : t("common.preview")
              }
            >
              {previewMode ? (
                <Code2 size={16} strokeWidth={2} />
              ) : (
                <Eye size={16} strokeWidth={2} />
              )}
            </button>
          </Tooltip>
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
            disabled={fileMissing}
            aria-label={t("common.download")}
          >
            <ArrowDownToLine size={16} strokeWidth={2} />
          </button>
        </Tooltip>
        {showEditButton &&
          (editMode ? (
            <Tooltip title={t("common.save")}>
              <button
                type="button"
                className={`${styles.fileModalIconBtn} ${styles.fileModalIconBtnPrimary}`}
                onClick={() => void save()}
                disabled={saving}
                aria-label={t("common.save")}
              >
                <Save size={16} strokeWidth={2} />
              </button>
            </Tooltip>
          ) : (
            <Tooltip title={t("common.edit")}>
              <button
                type="button"
                className={styles.fileModalIconBtn}
                onClick={() => {
                  setPreviewMode(false);
                  setEditMode(true);
                }}
                aria-label={t("common.edit")}
              >
                <Pencil size={16} strokeWidth={2} />
              </button>
            </Tooltip>
          ))}
      </>
    );

    onActionsChange(actions);
  }, [
    onActionsChange,
    resolvedPath,
    showPreviewToggle,
    previewMode,
    refresh,
    download,
    save,
    fileLoading,
    fileMissing,
    showEditButton,
    editMode,
    saving,
    t,
  ]);

  useEffect(() => {
    return () => {
      onActionsChange?.(null);
    };
  }, [onActionsChange]);

  return (
    <div className={styles.filePanelBody}>
      <div
        className={`${styles.fileModalBody} ${
          bodyFill ? styles.fileModalBodyFill : ""
        }`}
      >
        {fileMissing ? (
          <div className={styles.fileMissingState} role="status">
            <FileX
              size={40}
              strokeWidth={1.5}
              className={styles.fileMissingIcon}
              aria-hidden
            />
            <p className={styles.fileMissingTitle}>
              {t("workspace.fileMaybeDeleted", "文件可能已被删除")}
            </p>
          </div>
        ) : (
          resolvedPath && (
            <FileViewer
              agentId={agentId}
              path={resolvedPath}
              fromWorkspace={false}
              editMode={editMode}
              value={content}
              onChange={setContent}
              fileLoading={fileLoading}
              previewMode={previewMode}
              refreshToken={refreshToken}
            />
          )
        )}
      </div>
    </div>
  );
}
