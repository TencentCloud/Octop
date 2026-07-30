import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Button, Select, message, Tooltip, Segmented } from "antd";
import { Pencil, Save, ArrowDownToLine, RefreshCw, FileX } from "lucide-react";
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

/** Display basename for dock title / select labels. */
function fileBasename(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts[parts.length - 1] || path;
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

export interface FilePanelChrome {
  title: ReactNode;
  actions: ReactNode;
}

interface FilePanelContentProps {
  agentId: string;
  /** All workspace files written by the agent in this thread. */
  filePaths: string[];
  /** When set, opens on this path instead of the latest written one. */
  initialPath?: string | null;
  /** Lift title + actions into the shared dock shell toolbar. */
  onChromeChange?: (chrome: FilePanelChrome | null) => void;
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
  onChromeChange,
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
  const [fileMissing, setFileMissing] = useState(false);
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
    () => panelApiRequestPath(resolvedPath),
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
      a.download = fileBasename(resolvedPath) || "download";
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
    if (!onChromeChange) return;

    const title =
      normalizedPaths.length > 1 ? (
        <Select
          size="small"
          value={resolvedPath}
          onChange={setSelectedPath}
          className={styles.fileModalSelect}
          aria-label={t("chat.fileSwitch", "切换文件")}
          options={normalizedPaths.map((p) => ({
            value: p,
            label: fileBasename(p),
            title: p,
          }))}
          title={resolvedPath}
        />
      ) : resolvedPath ? (
        <span className={styles.fileModalName} title={resolvedPath}>
          {fileBasename(resolvedPath)}
        </span>
      ) : null;

    const actions = (
      <>
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
            disabled={fileMissing}
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
      </>
    );

    onChromeChange({ title, actions });
  }, [
    onChromeChange,
    normalizedPaths,
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
      onChromeChange?.(null);
    };
  }, [onChromeChange]);

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
