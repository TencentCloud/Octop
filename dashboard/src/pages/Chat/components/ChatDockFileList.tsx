import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Empty, Popconfirm, Tooltip } from "antd";
import { ChevronDown, ChevronRight, Download, Info, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { requestBlob } from "../../../api/request";
import { workspaceApi } from "../../../api/modules/workspace";
import { isNotFoundApiError } from "../../../utils/apiError";
import { fileTreeIcon } from "../../../utils/fileTreeIcon";
import {
  buildDockPathTree,
  canonicalizeDockFilePath,
  collectDockFolderPaths,
  dedupeDockFilePaths,
  dockFileBasename,
  mergeDockExpandedFolders,
  toDockWorkspaceApiPath,
  type DockPathTreeNode,
} from "../utils/dockFilePath";
import styles from "../index.module.less";

interface ChatDockFileListProps {
  agentId: string;
  filePaths: string[];
  onOpenFile: (path: string) => void;
  /** Called after a file is deleted so its viewer tab can be closed. */
  onCloseFile?: (path: string) => void;
}

function FolderRow({
  node,
  depth,
  expanded,
  onToggle,
}: {
  node: DockPathTreeNode;
  depth: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const fullPathLabel = node.path
    .replace(/\\/g, "/")
    .split("/")
    .filter(Boolean)
    .join(" / ");
  return (
    <button
      type="button"
      className={styles.dockFileTreeFolder}
      style={{ paddingLeft: 10 + depth * 14 }}
      onClick={onToggle}
      aria-expanded={expanded}
      title={node.path}
    >
      {expanded ? (
        <ChevronDown size={15} strokeWidth={2} aria-hidden />
      ) : (
        <ChevronRight size={15} strokeWidth={2} aria-hidden />
      )}
      <span className={styles.dockFileTreeFolderName}>
        {fullPathLabel || node.name}
      </span>
    </button>
  );
}

function FileRow({
  node,
  depth,
  downloading,
  deleting,
  onOpen,
  onDownload,
  onDelete,
  downloadLabel,
}: {
  node: DockPathTreeNode;
  depth: number;
  downloading: boolean;
  deleting: boolean;
  onOpen: () => void;
  onDownload: () => void;
  onDelete: () => void;
  downloadLabel: string;
}) {
  const { t } = useTranslation();
  const deleteLabel = t("chat.dockFileDelete", "删除文件");
  return (
    <div
      className={styles.dockFileTreeFile}
      style={{ paddingLeft: 10 + depth * 14 }}
    >
      <button
        type="button"
        className={styles.dockFileTreeFileMain}
        onClick={onOpen}
        title={node.path}
      >
        <span className={styles.dockFileTreeIcon} aria-hidden>
          {fileTreeIcon(node.path, 15)}
        </span>
        <span className={styles.dockFileTreeFileName}>
          {dockFileBasename(node.path)}
        </span>
      </button>
      <div className={styles.dockFileTreeActions}>
        <Tooltip title={deleteLabel}>
          <Popconfirm
            title={t(
              "chat.dockFileDeleteConfirm",
              "确定删除该文件吗？删除后不可恢复。",
            )}
            okText={t("common.delete", "删除")}
            cancelText={t("common.cancel", "取消")}
            okButtonProps={{ danger: true }}
            onConfirm={() => onDelete()}
            disabled={downloading || deleting}
          >
            <button
              type="button"
              className={styles.dockFileTreeDelete}
              onClick={(e) => e.stopPropagation()}
              disabled={downloading || deleting}
              aria-label={deleteLabel}
            >
              <Trash2 size={15} strokeWidth={2} />
            </button>
          </Popconfirm>
        </Tooltip>
        <Tooltip title={downloadLabel}>
          <button
            type="button"
            className={styles.dockFileTreeDownload}
            onClick={(e) => {
              e.stopPropagation();
              onDownload();
            }}
            disabled={downloading || deleting}
            aria-label={downloadLabel}
          >
            <Download size={15} strokeWidth={2} />
          </button>
        </Tooltip>
      </div>
    </div>
  );
}

function TreeNodes({
  nodes,
  depth,
  expanded,
  toggle,
  downloading,
  deleting,
  onOpenFile,
  onDownload,
  onDelete,
  downloadLabel,
}: {
  nodes: DockPathTreeNode[];
  depth: number;
  expanded: Set<string>;
  toggle: (path: string) => void;
  downloading: string | null;
  deleting: string | null;
  onOpenFile: (path: string) => void;
  onDownload: (path: string) => void;
  onDelete: (path: string) => void;
  downloadLabel: string;
}) {
  return (
    <>
      {nodes.map((node) => {
        if (node.isDir) {
          const open = expanded.has(node.path);
          return (
            <div key={`d:${node.path}`}>
              <FolderRow
                node={node}
                depth={depth}
                expanded={open}
                onToggle={() => toggle(node.path)}
              />
              {open ? (
                <TreeNodes
                  nodes={node.children}
                  depth={depth + 1}
                  expanded={expanded}
                  toggle={toggle}
                  downloading={downloading}
                  deleting={deleting}
                  onOpenFile={onOpenFile}
                  onDownload={onDownload}
                  onDelete={onDelete}
                  downloadLabel={downloadLabel}
                />
              ) : null}
            </div>
          );
        }
        return (
          <FileRow
            key={`f:${node.path}`}
            node={node}
            depth={depth}
            downloading={downloading === node.path}
            deleting={deleting === node.path}
            onOpen={() => onOpenFile(node.path)}
            onDownload={() => onDownload(node.path)}
            onDelete={() => onDelete(node.path)}
            downloadLabel={downloadLabel}
          />
        );
      })}
    </>
  );
}

/**
 * PR-style path tree of tool-produced workspace files (no checkboxes / dates).
 */
export default function ChatDockFileList({
  agentId,
  filePaths,
  onOpenFile,
  onCloseFile,
}: ChatDockFileListProps) {
  const { t } = useTranslation();
  // Deleted files stay in message-derived filePaths; hide them by canonical key.
  const [deletedKeys, setDeletedKeys] = useState<Set<string>>(() => new Set());
  const paths = useMemo(
    () =>
      dedupeDockFilePaths(filePaths, agentId).filter(
        (p) => !deletedKeys.has(canonicalizeDockFilePath(p, agentId)),
      ),
    [filePaths, agentId, deletedKeys],
  );
  const tree = useMemo(
    () => buildDockPathTree(paths, agentId),
    [paths, agentId],
  );
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [downloading, setDownloading] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const seenFoldersRef = useRef<Set<string>>(new Set());

  // Expand newly appeared folders only; keep user collapse state.
  useEffect(() => {
    const folders = collectDockFolderPaths(tree);
    setExpanded((prev) => {
      const { expanded: next, seen } = mergeDockExpandedFolders(
        prev,
        folders,
        seenFoldersRef.current,
      );
      seenFoldersRef.current = seen;
      return next;
    });
  }, [tree]);

  const toggle = useCallback((path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const handleDownload = useCallback(
    async (path: string) => {
      if (!agentId || !path) return;
      setDownloading(path);
      try {
        const blob = await requestBlob(
          `/agents/${encodeURIComponent(
            agentId,
          )}/workspace/download?path=${encodeURIComponent(
            toDockWorkspaceApiPath(path, agentId),
          )}`,
        );
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = dockFileBasename(path) || "download";
        a.click();
        URL.revokeObjectURL(a.href);
      } catch (err: unknown) {
        if (isNotFoundApiError(err)) {
          message.warning(
            t(
              "chat.dockFileMaybeDeleted",
              "该文件可能为处理过程中的临时文件，当前已经被删除。",
            ),
          );
          return;
        }
        message.error(
          (err instanceof Error ? err.message : String(err)) ||
            t("workspace.downloadFailed", "下载失败"),
        );
      } finally {
        setDownloading(null);
      }
    },
    [agentId, t],
  );

  /** Hide a path from the list (by canonical key) and close its viewer tab. */
  const hideDeletedPath = useCallback(
    (path: string) => {
      const key = canonicalizeDockFilePath(path, agentId);
      if (key) {
        setDeletedKeys((prev) => {
          if (prev.has(key)) return prev;
          const next = new Set(prev);
          next.add(key);
          return next;
        });
      }
      onCloseFile?.(path);
    },
    [agentId, onCloseFile],
  );

  const handleDelete = useCallback(
    async (path: string) => {
      if (!agentId || !path) return;
      setDeleting(path);
      try {
        await workspaceApi.deleteWorkspaceFile(
          agentId,
          toDockWorkspaceApiPath(path, agentId),
        );
        message.success(t("workspace.deleteSuccess", "已删除"));
        hideDeletedPath(path);
      } catch (err: unknown) {
        if (isNotFoundApiError(err)) {
          message.warning(
            t(
              "chat.dockFileMaybeDeleted",
              "该文件可能为处理过程中的临时文件，当前已经被删除。",
            ),
          );
          hideDeletedPath(path);
          return;
        }
        message.error(
          (err instanceof Error ? err.message : String(err)) ||
            t("workspace.deleteFailed", "删除失败"),
        );
      } finally {
        setDeleting(null);
      }
    },
    [agentId, hideDeletedPath, t],
  );

  const listHint = (
    <div className={styles.dockFileListHint} role="note">
      <Info
        size={14}
        strokeWidth={2}
        className={styles.dockFileListHintIcon}
        aria-hidden
      />
      <p>
        {t(
          "chat.dockFileListHint",
          "当前仅列出执行过程中生成的文件，不代表最终一定存储，可能在处理结束后被大模型删除。",
        )}
      </p>
    </div>
  );

  if (paths.length === 0) {
    return (
      <div className={styles.dockFileList}>
        {listHint}
        <div className={styles.dockFileListEmpty}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t(
              "chat.dockFileListEmpty",
              "暂无工具生成或发送的文件",
            )}
          />
        </div>
      </div>
    );
  }

  const downloadLabel = t("common.download", "下载");

  return (
    <div className={styles.dockFileList}>
      {listHint}
      <div className={styles.dockFileTreeWrap}>
        <div className={styles.dockFileTreeSummary}>
          {t("chat.dockFileListCount", {
            count: paths.length,
            defaultValue: "{{count}} 个文件",
          })}
        </div>
        <div className={styles.dockFileTree}>
          <TreeNodes
            nodes={tree}
            depth={0}
            expanded={expanded}
            toggle={toggle}
            downloading={downloading}
            deleting={deleting}
            onOpenFile={onOpenFile}
            onDownload={(p) => void handleDownload(p)}
            onDelete={(p) => void handleDelete(p)}
            downloadLabel={downloadLabel}
          />
        </div>
      </div>
    </div>
  );
}
