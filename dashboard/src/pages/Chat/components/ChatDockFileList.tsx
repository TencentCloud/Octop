import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Empty, Tooltip } from "antd";
import { ChevronDown, ChevronRight, Download, Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { requestBlob } from "../../../api/request";
import { isNotFoundApiError } from "../../../utils/apiError";
import { fileTreeIcon } from "../../../utils/fileTreeIcon";
import {
  buildDockPathTree,
  collectDockFolderPaths,
  dockFileBasename,
  listDockFilePathsForTree,
  mergeDockExpandedFolders,
  toDockWorkspaceApiPath,
  type DockPathTreeNode,
} from "../utils/dockFilePath";
import styles from "../index.module.less";

interface ChatDockFileListProps {
  agentId: string;
  filePaths: string[];
  onOpenFile: (path: string) => void;
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
      <span className={styles.dockFileTreeFolderName}>{node.name}</span>
    </button>
  );
}

function FileRow({
  node,
  depth,
  downloading,
  onOpen,
  onDownload,
  downloadLabel,
}: {
  node: DockPathTreeNode;
  depth: number;
  downloading: boolean;
  onOpen: () => void;
  onDownload: () => void;
  downloadLabel: string;
}) {
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
      <Tooltip title={downloadLabel}>
        <button
          type="button"
          className={styles.dockFileTreeDownload}
          onClick={(e) => {
            e.stopPropagation();
            onDownload();
          }}
          disabled={downloading}
          aria-label={downloadLabel}
        >
          <Download size={15} strokeWidth={2} />
        </button>
      </Tooltip>
    </div>
  );
}

function TreeNodes({
  nodes,
  depth,
  expanded,
  toggle,
  downloading,
  onOpenFile,
  onDownload,
  downloadLabel,
}: {
  nodes: DockPathTreeNode[];
  depth: number;
  expanded: Set<string>;
  toggle: (path: string) => void;
  downloading: string | null;
  onOpenFile: (path: string) => void;
  onDownload: (path: string) => void;
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
                  onOpenFile={onOpenFile}
                  onDownload={onDownload}
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
            onOpen={() => onOpenFile(node.path)}
            onDownload={() => onDownload(node.path)}
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
}: ChatDockFileListProps) {
  const { t } = useTranslation();
  const paths = useMemo(
    () => listDockFilePathsForTree(filePaths, agentId),
    [filePaths, agentId],
  );
  const tree = useMemo(
    () => buildDockPathTree(paths, agentId),
    [paths, agentId],
  );
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [downloading, setDownloading] = useState<string | null>(null);
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
            onOpenFile={onOpenFile}
            onDownload={(p) => void handleDownload(p)}
            downloadLabel={downloadLabel}
          />
        </div>
      </div>
    </div>
  );
}
