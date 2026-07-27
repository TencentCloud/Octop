/**
 * StorageBrowseDrawer — browse files/directories on a configured storage backend.
 */
import { useCallback, useEffect, useState } from "react";
import { Drawer, Empty, Spin, Tree, message } from "antd";
import type { TreeDataNode } from "antd";
import { Folder, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import { fileTreeIcon } from "../../../utils/fileTreeIcon";
import { workspaceEntryPath } from "../../../utils/workspacePath";
import type { StorageBackendRow } from "./useStorageBackends";
import styles from "./storage.module.less";

interface FileInfo {
  path: string;
  is_dir?: boolean;
  size?: number;
}

interface TreeKey {
  path: string;
  is_dir: boolean;
}

interface StorageBrowseDrawerProps {
  open: boolean;
  onClose: () => void;
  backend: StorageBackendRow | null;
}

function nodeKey(t: TreeKey): string {
  return `${t.is_dir ? "d" : "f"}:${t.path}`;
}

function pathFromKey(key: string): TreeKey {
  const sep = key.indexOf(":");
  return { is_dir: key[0] === "d", path: key.slice(sep + 1) };
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function toTreeNodes(infos: FileInfo[]): TreeDataNode[] {
  const sorted = [...infos].sort((a, b) => {
    const ad = a.is_dir ? 0 : 1;
    const bd = b.is_dir ? 0 : 1;
    if (ad !== bd) return ad - bd;
    const an = (
      a.path.split("/").filter(Boolean).pop() || a.path
    ).toLowerCase();
    const bn = (
      b.path.split("/").filter(Boolean).pop() || b.path
    ).toLowerCase();
    return an.localeCompare(bn);
  });

  return sorted.map((info) => {
    const fullPath = workspaceEntryPath(info.path);
    const fname = fullPath.split("/").filter(Boolean).pop() || fullPath;
    const key = nodeKey({ path: fullPath, is_dir: !!info.is_dir });
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

  const fetchTree = useCallback(
    async (path: string) => {
      if (!backend) return [];
      return request<FileInfo[]>(
        `/admin/storage-backends/${backend.id}/tree?path=${encodeURIComponent(
          path,
        )}`,
      );
    },
    [backend],
  );

  const refreshRoot = useCallback(async () => {
    if (!backend) return;
    setLoading(true);
    try {
      const data = await fetchTree("/");
      setTreeData(toTreeNodes(data));
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("storage.browseFailed"),
      );
      setTreeData([]);
    } finally {
      setLoading(false);
    }
  }, [backend, fetchTree, t]);

  useEffect(() => {
    if (open && backend) {
      setTreeData([]);
      void refreshRoot();
    }
  }, [open, backend, refreshRoot]);

  const onLoadData = async (node: TreeDataNode): Promise<void> => {
    const { path, is_dir } = pathFromKey(String(node.key));
    if (!is_dir) return;
    try {
      const data = await fetchTree(path);
      const children = toTreeNodes(data);
      const replace = (nodes: TreeDataNode[]): TreeDataNode[] =>
        nodes.map((n) =>
          n.key === node.key
            ? { ...n, children }
            : n.children
            ? { ...n, children: replace(n.children) }
            : n,
        );
      setTreeData((d) => replace(d));
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("storage.browseLoadFailed"),
      );
    }
  };

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
      {loading ? (
        <div className={styles.loadingState}>
          <Spin />
        </div>
      ) : treeData.length === 0 ? (
        <Empty description={t("storage.browseEmpty")} />
      ) : (
        <Tree
          showLine
          blockNode
          loadData={onLoadData}
          treeData={treeData}
          className={styles.browseTree}
        />
      )}
    </Drawer>
  );
}
