import { useCallback, useEffect, useState } from "react";
import { Spin, Tooltip, Tree } from "antd";
import type { TreeDataNode } from "antd";
import { Folder, PanelLeftClose } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { request } from "../../../../api/request";
import { withFromWorkspace } from "../../../../utils/fromWorkspace";
import { fileTreeIcon } from "../../../../utils/fileTreeIcon";
import { workspaceEntryPath } from "../../../../utils/workspacePath";
import styles from "./SkillFileTree.module.less";

interface FileInfo {
  path: string;
  is_dir?: boolean;
  size?: number;
}

interface TreeKey {
  path: string;
  is_dir: boolean;
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
        <span className={styles.treeNodeTitle}>
          {info.is_dir ? (
            <Folder size={13} className={styles.treeFileIcon} aria-hidden />
          ) : (
            <span className={styles.treeFileIcon}>
              {fileTreeIcon(fullPath)}
            </span>
          )}
          <span className={styles.treeNodeName}>{fname}</span>
          {info.size != null && !info.is_dir ? (
            <span className={styles.treeNodeSize}>{formatSize(info.size)}</span>
          ) : null}
        </span>
      ),
      isLeaf: !info.is_dir,
      children: info.is_dir ? [] : undefined,
    } as TreeDataNode;
  });
}

/** Strip leading ``/skills/{slug}/`` so package APIs get a skill-relative path. */
export function packageSkillRelativePath(
  fullPath: string,
  skillRoot: string,
): string {
  const normalized = fullPath.replace(/\\/g, "/").replace(/^\/+/, "");
  const root = skillRoot
    .replace(/\\/g, "/")
    .replace(/^\/+/, "")
    .replace(/\/+$/, "");
  if (!root) return normalized;
  if (normalized === root) return "";
  const prefix = `${root}/`;
  return normalized.startsWith(prefix)
    ? normalized.slice(prefix.length)
    : normalized;
}

export type SkillFileTreeSource =
  | {
      type: "workspace";
      agentId: string;
      skillRoot: string;
      workspaceReady: boolean;
    }
  | {
      type: "package";
      packageId: string;
      slug: string;
      skillRoot: string;
    };

interface SkillFileTreeProps {
  source: SkillFileTreeSource;
  selectedPath: string | null;
  onSelectPath: (path: string) => void;
  onCollapse: () => void;
  selectionDisabled?: boolean;
}

export function SkillFileTree({
  source,
  selectedPath,
  onSelectPath,
  onCollapse,
  selectionDisabled = false,
}: SkillFileTreeProps) {
  const { t } = useTranslation();
  const [treeData, setTreeData] = useState<TreeDataNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);

  const skillRoot = source.skillRoot;
  const sourceType = source.type;
  const packageId = source.type === "package" ? source.packageId : "";
  const packageSlug = source.type === "package" ? source.slug : "";
  const agentId = source.type === "workspace" ? source.agentId : "";
  const treeReady =
    source.type === "package" ? true : Boolean(source.workspaceReady);

  const fetchTree = useCallback(
    async (path: string) => {
      if (sourceType === "package") {
        const relative = packageSkillRelativePath(path, skillRoot);
        const qs = relative ? `?path=${encodeURIComponent(relative)}` : "";
        return request<FileInfo[]>(
          `/skill-packages/${encodeURIComponent(
            packageId,
          )}/skills/${encodeURIComponent(packageSlug)}/tree${qs}`,
        );
      }
      return request<FileInfo[]>(
        withFromWorkspace(
          `/agents/${agentId}/workspace/tree?path=${encodeURIComponent(path)}`,
        ),
      );
    },
    [agentId, packageId, packageSlug, skillRoot, sourceType],
  );

  const refreshRoot = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchTree(skillRoot);
      setTreeData(toTreeNodes(data));
    } catch {
      setTreeData([]);
    } finally {
      setLoading(false);
    }
  }, [fetchTree, skillRoot]);

  useEffect(() => {
    if (!treeReady) {
      setExpandedKeys([]);
      setTreeData([]);
      setLoading(false);
      return;
    }
    setExpandedKeys([]);
    setTreeData([]);
    void refreshRoot();
  }, [
    agentId,
    packageId,
    packageSlug,
    refreshRoot,
    skillRoot,
    sourceType,
    treeReady,
  ]);

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
      setTreeData((current) => replace(current));
    } catch {
      /* ignore — tree node stays empty */
    }
  };

  const selectedKey = selectedPath
    ? nodeKey({ path: selectedPath, is_dir: false })
    : undefined;

  return (
    <div className={styles.treePane}>
      <div className={styles.treeHeader}>
        <span className={styles.treeHeaderTitle}>
          {t("skills.fileTreeTitle")}
        </span>
        <Tooltip title={t("skills.fileTreeHide")}>
          <button
            type="button"
            className={styles.treeHeaderToggle}
            onClick={onCollapse}
            aria-label={t("skills.fileTreeHide")}
          >
            <PanelLeftClose size={15} strokeWidth={1.8} />
          </button>
        </Tooltip>
      </div>
      <div className={styles.treeScroll}>
        {!treeReady ? (
          <div className={styles.treeEmpty}>
            {t("skills.fileTreeAgentNotReady")}
          </div>
        ) : loading ? (
          <div className={styles.treeLoading}>
            <Spin size="small" />
          </div>
        ) : treeData.length === 0 ? (
          <div className={styles.treeEmpty}>{t("skills.fileTreeEmpty")}</div>
        ) : (
          <Tree
            showLine
            blockNode
            loadData={onLoadData}
            treeData={treeData}
            expandedKeys={expandedKeys}
            onExpand={(keys) => setExpandedKeys(keys as string[])}
            selectedKeys={selectedKey ? [selectedKey] : []}
            onSelect={(_keys, info) => {
              if (selectionDisabled) {
                message.warning(t("skills.finishEditBeforeSwitchFile"));
                return;
              }
              const { path, is_dir } = pathFromKey(String(info.node.key));
              if (is_dir) return;
              onSelectPath(path);
            }}
            className={styles.tree}
          />
        )}
      </div>
    </div>
  );
}
