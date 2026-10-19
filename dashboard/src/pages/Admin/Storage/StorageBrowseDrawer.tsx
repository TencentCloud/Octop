/**
 * StorageBrowseDrawer — browse files/directories on a configured storage backend.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Drawer, Empty, Modal, Spin, Tree } from "antd";
import { message } from "@/utils/antdMessage";

import type { TreeDataNode } from "antd";
import { ArrowDownToLine, Folder, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request, requestBlob } from "../../../api/request";
import { fileTreeIcon } from "../../../utils/fileTreeIcon";
import {
  dedupeFileTreeInfos,
  nodeKey,
  pathFromKey,
} from "../../../utils/fileTreeNodes";
import { saveBlobAsFile } from "../../../utils/saveBlobAsFile";
import { workspaceEntryPath } from "../../../utils/workspacePath";
import FileViewer from "../../Agent/Workspace/components/FileViewer";
import {
  defaultPreviewMode,
  getPreviewKind,
  previewNeedsFillLayout,
} from "../../Agent/Workspace/components/FilePreview";
import { getDocKind } from "../../Agent/Workspace/utils/docKind";
import { isProbablyText } from "../../Agent/Workspace/utils/fileKind";
import { getMediaKind } from "../../Agent/Workspace/utils/mediaKind";
import { storageBrowseError } from "./storageProbeMessage";
import type { StorageBackendRow } from "./useStorageBackends";
import styles from "./storage.module.less";

interface FileInfo {
  path: string;
  is_dir?: boolean;
  size?: number;
}

interface StorageBrowseDrawerProps {
  open: boolean;
  onClose: () => void;
  backend: StorageBackendRow | null;
}

const STORAGE_ROOT_PATH = "/";

function storageRootKey(): string {
  return nodeKey(STORAGE_ROOT_PATH, true);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function storageFileUrl(
  backendId: number,
  path: string,
  kind: "file" | "download",
  opts?: { preview?: boolean },
): string {
  const params = new URLSearchParams({ path });
  if (kind === "download" && opts?.preview) params.set("preview", "true");
  return `/admin/storage-backends/${backendId}/${kind}?${params.toString()}`;
}

function canPreviewPath(path: string): boolean {
  return Boolean(
    getMediaKind(path) || getDocKind(path) || isProbablyText(path),
  );
}

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

function pathDepth(key: string): number {
  return pathFromKey(key).path.split("/").filter(Boolean).length;
}

function replaceNodeChildren(
  nodes: TreeDataNode[],
  key: string,
  children: TreeDataNode[],
): TreeDataNode[] {
  return nodes.map((n) => {
    if (n.key === key) return { ...n, children };
    if (n.children) {
      return { ...n, children: replaceNodeChildren(n.children, key, children) };
    }
    return n;
  });
}

function toTreeNodes(infos: FileInfo[], listedPath?: string): TreeDataNode[] {
  return dedupeFileTreeInfos(infos, listedPath).map((info) => {
    const fullPath = workspaceEntryPath(info.path);
    const fname = fullPath.split("/").filter(Boolean).pop() || fullPath;
    const key = nodeKey(fullPath, !!info.is_dir);
    return {
      key,
      title: (
        <span className={styles.browseTreeNode}>
          {info.is_dir ? (
            <Folder size={13} className={styles.browseTreeIcon} aria-hidden />
          ) : (
            <span className={styles.browseTreeIcon}>
              {fileTreeIcon(fullPath)}
            </span>
          )}
          <span>{fname}</span>
          {info.size != null && !info.is_dir && (
            <span className={styles.browseTreeSize}>
              {formatSize(info.size)}
            </span>
          )}
        </span>
      ),
      isLeaf: !info.is_dir,
      children: info.is_dir ? [] : undefined,
    } as TreeDataNode;
  });
}

export function StorageBrowseDrawer({
  open,
  onClose,
  backend,
}: StorageBrowseDrawerProps) {
  const { t } = useTranslation();
  const [treeData, setTreeData] = useState<TreeDataNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([
    storageRootKey(),
  ]);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [downloadPrompt, setDownloadPrompt] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [fileLoading, setFileLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const expandedKeysRef = useRef(expandedKeys);
  expandedKeysRef.current = expandedKeys;

  const buildStorageRootNode = useCallback(
    (children: TreeDataNode[]): TreeDataNode => ({
      key: storageRootKey(),
      title: (
        <span className={styles.browseTreeNode}>
          <Folder size={13} className={styles.browseTreeIcon} aria-hidden />
          <span>{STORAGE_ROOT_PATH}</span>
        </span>
      ),
      isLeaf: false,
      children,
    }),
    [],
  );

  const backendId = backend?.id;

  const fetchTree = useCallback(
    async (path: string) => {
      if (backendId == null) return [];
      return request<FileInfo[]>(
        `/admin/storage-backends/${backendId}/tree?path=${encodeURIComponent(
          path,
        )}`,
      );
    },
    [backendId],
  );

  const closePreview = useCallback(() => {
    abortRef.current?.abort();
    setPreviewPath(null);
    setContent("");
    setFileLoading(false);
  }, []);

  const releaseBrowse = useCallback(() => {
    if (backendId == null) return;
    abortRef.current?.abort();
    void request(`/admin/storage-backends/${backendId}/browse`, {
      method: "DELETE",
    }).catch(() => undefined);
  }, [backendId]);

  const refreshRoot = useCallback(async () => {
    if (backendId == null) return;
    const keepExpanded = [...expandedKeysRef.current];
    setLoading(true);
    try {
      const data = await fetchTree("/");
      let nodes = [buildStorageRootNode(toTreeNodes(data, STORAGE_ROOT_PATH))];
      const dirs = keepExpanded
        .filter((key) => key !== storageRootKey())
        .sort((a, b) => pathDepth(a) - pathDepth(b));
      for (const key of dirs) {
        const { path, is_dir } = pathFromKey(key);
        if (!is_dir) continue;
        try {
          const children = toTreeNodes(await fetchTree(path), path);
          nodes = replaceNodeChildren(nodes, key, children);
        } catch {
          // Keep the collapsed placeholder; expand will retry.
        }
      }
      setTreeData(nodes);
      setExpandedKeys(keepExpanded.length ? keepExpanded : [storageRootKey()]);
      setLoadError(false);
    } catch (err) {
      message.error(storageBrowseError(err, t));
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [backendId, fetchTree, t, buildStorageRootNode]);

  useEffect(() => {
    if (!open || !backend) return;
    setTreeData([]);
    setLoadError(false);
    expandedKeysRef.current = [storageRootKey()];
    setExpandedKeys([storageRootKey()]);
    void refreshRoot();
    return () => {
      closePreview();
      setDownloadPrompt(null);
      releaseBrowse();
    };
  }, [open, backendId, refreshRoot, closePreview, releaseBrowse]);

  const onLoadData = async (node: TreeDataNode): Promise<void> => {
    const { path, is_dir } = pathFromKey(String(node.key));
    if (!is_dir) return;
    try {
      const data = await fetchTree(path);
      const children = toTreeNodes(data, path);
      setTreeData((d) => replaceNodeChildren(d, String(node.key), children));
    } catch (err) {
      message.error(storageBrowseError(err, t));
    }
  };

  const downloadFile = async (path: string) => {
    if (!backend) return;
    const filename = path.split("/").filter(Boolean).pop() || "download.bin";
    try {
      const blob = await requestBlob(
        storageFileUrl(backend.id, path, "download"),
      );
      await saveBlobAsFile(blob, filename);
    } catch (err) {
      message.error(storageBrowseError(err, t));
    }
  };

  const openFile = async (path: string) => {
    if (!backend) return;
    if (!canPreviewPath(path)) {
      setDownloadPrompt(path);
      return;
    }
    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;
    setPreviewPath(path);
    setContent("");
    if (getMediaKind(path) || getDocKind(path)) return;
    setFileLoading(true);
    try {
      const r = await request<{ content: string }>(
        storageFileUrl(backend.id, path, "file"),
        { signal: abort.signal },
      );
      if (abort.signal.aborted) return;
      setContent(r.content);
    } catch (err) {
      if (isAbortError(err) || abort.signal.aborted) return;
      message.error(storageBrowseError(err, t));
      setPreviewPath(null);
    } finally {
      if (!abort.signal.aborted) setFileLoading(false);
    }
  };

  const previewName = previewPath
    ? previewPath.split("/").filter(Boolean).pop() || previewPath
    : "";
  const downloadName = downloadPrompt
    ? downloadPrompt.split("/").filter(Boolean).pop() || downloadPrompt
    : "";
  const fillPreview =
    previewPath != null &&
    (getDocKind(previewPath) != null ||
      previewNeedsFillLayout(getPreviewKind(previewPath)));

  return (
    <Drawer
      title={
        backend
          ? t("storage.browseTitle", { name: backend.name })
          : t("storage.browse")
      }
      open={open}
      onClose={onClose}
      destroyOnHidden
      width={480}
      extra={
        <button
          type="button"
          className={styles.browseRefreshBtn}
          onClick={() => void refreshRoot()}
          disabled={loading || !backend}
          aria-label={t("common.refresh")}
        >
          <RefreshCw size={14} />
        </button>
      }
    >
      {loading && treeData.length === 0 ? (
        <div className={styles.loadingState}>
          <Spin />
        </div>
      ) : treeData.length === 0 ? (
        <Empty
          description={
            loadError ? t("storage.browseFailed") : t("storage.browseEmpty")
          }
        />
      ) : (
        <Tree
          showLine
          blockNode
          loadData={onLoadData}
          treeData={treeData}
          expandedKeys={expandedKeys}
          selectedKeys={previewPath ? [nodeKey(previewPath, false)] : []}
          onExpand={(keys) => setExpandedKeys(keys.map(String))}
          onSelect={(keys) => {
            if (!keys.length) return;
            const { path, is_dir } = pathFromKey(String(keys[0]));
            if (is_dir) return;
            void openFile(path);
          }}
          className={styles.browseTree}
        />
      )}
      <Modal
        title={previewName}
        open={previewPath != null}
        onCancel={closePreview}
        destroyOnHidden
        width={fillPreview ? "min(900px, 92vw)" : 640}
        footer={
          <Button
            icon={<ArrowDownToLine size={14} />}
            onClick={() => {
              if (previewPath) void downloadFile(previewPath);
            }}
          >
            {t("common.download")}
          </Button>
        }
      >
        {previewPath && backend ? (
          <div
            className={
              fillPreview ? styles.browsePreviewFill : styles.browsePreviewBody
            }
          >
            <FileViewer
              path={previewPath}
              fetchUrl={storageFileUrl(backend.id, previewPath, "download", {
                preview: true,
              })}
              editMode={false}
              value={content}
              onChange={setContent}
              fileLoading={fileLoading}
              previewMode={defaultPreviewMode(previewPath)}
            />
          </div>
        ) : null}
      </Modal>
      <Modal
        title={downloadName}
        open={downloadPrompt != null}
        onCancel={() => setDownloadPrompt(null)}
        okText={t("common.download")}
        cancelText={t("common.cancel")}
        onOk={() => {
          if (downloadPrompt) void downloadFile(downloadPrompt);
          setDownloadPrompt(null);
        }}
      >
        {t("storage.browseDownloadOnly")}
      </Modal>
    </Drawer>
  );
}
