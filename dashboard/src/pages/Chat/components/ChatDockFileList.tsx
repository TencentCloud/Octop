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
  type DockFileRef,
  type DockPathTreeNode,
} from "../utils/dockFilePath";
import styles from "../index.module.less";

interface ChatDockFileListProps {
  agentId: string;
  filePaths: Array<string | DockFileRef>;
  onOpenFile: (path: string, agentId?: string | null) => void;
  /** Map producer agent_id → display name (team file dock). */
  agentNameById?: Record<string, string>;
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
  agentLabel,
}: {
  node: DockPathTreeNode;
  depth: number;
  downloading: boolean;
  onOpen: () => void;
  onDownload: () => void;
  downloadLabel: string;
  agentLabel?: string;
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
        title={agentLabel ? `${node.path} · ${agentLabel}` : node.path}
      >
        <span className={styles.dockFileTreeIcon} aria-hidden>
          {fileTreeIcon(node.path, 15)}
        </span>
        <span className={styles.dockFileTreeFileMeta}>
          <span className={styles.dockFileTreeFileName}>
            {dockFileBasename(node.path)}
          </span>
          {agentLabel ? (
            <span className={styles.dockFileTreeFileAgent}>{agentLabel}</span>
          ) : null}
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
  defaultAgentId,
  agentNameById,
  showAgentLabels,
}: {
  nodes: DockPathTreeNode[];
  depth: number;
  expanded: Set<string>;
  toggle: (path: string) => void;
  downloading: string | null;
  onOpenFile: (path: string, agentId?: string | null) => void;
  onDownload: (path: string, agentId?: string | null) => void;
  downloadLabel: string;
  defaultAgentId: string;
  agentNameById?: Record<string, string>;
  showAgentLabels: boolean;
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
                  defaultAgentId={defaultAgentId}
                  agentNameById={agentNameById}
                  showAgentLabels={showAgentLabels}
                />
              ) : null}
            </div>
          );
        }
        const fileAgent = node.agentId || defaultAgentId;
        const downloadKey = `${fileAgent}\0${node.path}`;
        const agentLabel =
          showAgentLabels && fileAgent
            ? agentNameById?.[fileAgent] || fileAgent
            : undefined;
        return (
          <FileRow
            key={`f:${downloadKey}`}
            node={node}
            depth={depth}
            downloading={downloading === downloadKey}
            onOpen={() => onOpenFile(node.path, fileAgent)}
            onDownload={() => onDownload(node.path, fileAgent)}
            downloadLabel={downloadLabel}
            agentLabel={agentLabel}
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
  agentNameById,
}: ChatDockFileListProps) {
  const { t } = useTranslation();
  const refs = useMemo(
    () => listDockFilePathsForTree(filePaths, agentId),
    [filePaths, agentId],
  );
  const showAgentLabels = useMemo(() => {
    const ids = new Set(
      refs.map((ref) => (ref.agentId || agentId || "").trim()).filter(Boolean),
    );
    if (ids.size > 1) return true;
    const only = [...ids][0];
    return Boolean(only && only !== agentId);
  }, [refs, agentId]);
  const tree = useMemo(() => buildDockPathTree(refs, agentId), [refs, agentId]);
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
    async (path: string, fileAgentId?: string | null) => {
      const owner = (fileAgentId || agentId || "").trim();
      if (!owner || !path) return;
      const downloadKey = `${owner}\0${path}`;
      setDownloading(downloadKey);
      try {
        const blob = await requestBlob(
          `/agents/${encodeURIComponent(
            owner,
          )}/workspace/download?path=${encodeURIComponent(
            toDockWorkspaceApiPath(path, owner),
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

  if (refs.length === 0) {
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
            count: refs.length,
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
            onDownload={(p, aid) => void handleDownload(p, aid)}
            downloadLabel={downloadLabel}
            defaultAgentId={agentId}
            agentNameById={agentNameById}
            showAgentLabels={showAgentLabels}
          />
        </div>
      </div>
    </div>
  );
}
