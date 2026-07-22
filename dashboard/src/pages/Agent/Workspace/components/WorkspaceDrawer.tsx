/**
 * WorkspaceDrawer — full workspace browser inside an Ant Design Drawer.
 * Accepts `agentId` as a prop so it can be embedded from any context
 * without modifying the global active-agent selection.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Tree,
  Empty,
  Spin,
  Button,
  Space,
  Upload,
  message,
  Tooltip,
  Drawer,
  Modal,
  Radio,
  Segmented,
  Dropdown,
  Popconfirm,
  Input,
} from "antd";
import type { TreeDataNode, TreeProps } from "antd";
import {
  Folder,
  RefreshCw,
  Save,
  Upload as UploadIcon,
  ArrowDownToLine,
  Pencil,
  Archive,
  Download,
  Trash2,
  MoreHorizontal,
  ChevronLeft,
  ChevronRight,
  FolderPlus,
  FilePlus,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { request, requestBlob, requestUpload } from "../../../../api/request";
import { withFromWorkspace } from "@/utils/fromWorkspace";
import { workspaceApi } from "../../../../api/modules/workspace";
import { useAgent } from "../../../../context/AgentContext";
import { useIsMobile } from "../../../../hooks/useIsMobile";
import { useHorizontalResize } from "../../../../hooks/useHorizontalResize";
import { useServerTimezone } from "../../../../hooks/useServerTimezone";
import { formatServerIsoDateTime } from "../../../../utils/formatMessageTime";
import { isAgentChatReady } from "../../../../utils/agentError";
import AgentNotReadyScreen from "../../../Chat/components/AgentNotReadyScreen";
import { fileTreeIcon } from "../../../../utils/fileTreeIcon";
import { workspaceEntryPath } from "../../../../utils/workspacePath";
import FileViewer from "./FileViewer";
import {
  getPreviewKind,
  previewNeedsFillLayout,
  defaultPreviewMode,
} from "./FilePreview";
import { getMediaKind } from "../utils/mediaKind";
import { getDocKind } from "../utils/docKind";
import { isProbablyText } from "../utils/fileKind";
import styles from "../index.module.less";

interface FileInfo {
  path: string;
  is_dir?: boolean;
  size?: number;
  modified_at?: string;
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

function formatModified(ts: string | undefined, timeZone: string): string {
  if (!ts) return "—";
  return formatServerIsoDateTime(ts, timeZone);
}

function sortFileInfos(infos: FileInfo[]): FileInfo[] {
  return [...infos].sort((a, b) => {
    const ad = a.is_dir ? 0 : 1;
    const bd = b.is_dir ? 0 : 1;
    if (ad !== bd) return ad - bd;
    const an = (
      workspaceEntryPath(a.path).split("/").filter(Boolean).pop() || a.path
    ).toLowerCase();
    const bn = (
      workspaceEntryPath(b.path).split("/").filter(Boolean).pop() || b.path
    ).toLowerCase();
    return an.localeCompare(bn);
  });
}

type CreateKind = "file" | "folder";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function isProtectedPath(path: string): boolean {
  return path === "/_builtin_skills" || path.startsWith("/_builtin_skills/");
}

const WORKSPACE_ROOT_PATH = "/";

function workspaceRootKey(): string {
  return nodeKey({ path: WORKSPACE_ROOT_PATH, is_dir: true });
}

function isWorkspaceRoot(path: string): boolean {
  return path === "/" || path === ".";
}

function canCreateIn(path: string): boolean {
  return !isProtectedPath(path);
}

function canDeletePath(path: string): boolean {
  return !isWorkspaceRoot(path) && !isProtectedPath(path);
}

interface BreadcrumbSegment {
  label: string;
  path: string;
  isDir: boolean;
}

function buildBreadcrumbSegments(
  path: string,
  rootLabel: string,
  isDir: boolean,
): BreadcrumbSegment[] {
  const segments: BreadcrumbSegment[] = [
    { label: rootLabel, path: WORKSPACE_ROOT_PATH, isDir: true },
  ];
  if (isWorkspaceRoot(path)) return segments;

  const parts = path.split("/").filter(Boolean);
  let acc = "";
  for (let i = 0; i < parts.length; i += 1) {
    acc += `/${parts[i]}`;
    const isLast = i === parts.length - 1;
    segments.push({
      label: parts[i],
      path: acc,
      isDir: !isLast || isDir,
    });
  }
  return segments;
}

function expandedKeysForDir(dirPath: string): string[] {
  if (isWorkspaceRoot(dirPath)) return [workspaceRootKey()];

  const keys = [workspaceRootKey()];
  const parts = dirPath.split("/").filter(Boolean);
  let acc = "";
  for (const part of parts) {
    acc = joinPath(acc || WORKSPACE_ROOT_PATH, part);
    keys.push(nodeKey({ path: acc, is_dir: true }));
  }
  return keys;
}

const TREE_COLLAPSED_KEY = "octop:workspace-drawer-tree-collapsed";

function parentDir(path: string): string {
  const parts = path.split("/").filter(Boolean);
  parts.pop();
  return parts.length ? `/${parts.join("/")}` : "/";
}

function joinPath(dir: string, name: string): string {
  const base = dir.endsWith("/") ? dir.slice(0, -1) : dir;
  if (!base || base === "/") return `/${name}`;
  return `${base}/${name}`;
}

function isDescendantPath(ancestor: string, candidate: string): boolean {
  const a = ancestor.replace(/\/$/, "");
  const c = candidate.replace(/\/$/, "");
  return c === a || c.startsWith(`${a}/`);
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
          <span>{fname}</span>
          {info.size != null && !info.is_dir && (
            <span
              style={{
                marginLeft: 4,
                fontSize: 10,
                color: "var(--fn-text-tertiary)",
              }}
            >
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

interface WorkspaceDrawerProps {
  agentId: string;
  open: boolean;
  onClose: () => void;
}

export default function WorkspaceDrawer({
  agentId,
  open,
  onClose,
}: WorkspaceDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const timeZone = useServerTimezone();
  const { agents } = useAgent();
  const activeAgent = agents.find((a) => a.agent_id === agentId) ?? null;
  const workspaceReady = isAgentChatReady(activeAgent?.state);

  const [treeData, setTreeData] = useState<TreeDataNode[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [editMode, setEditMode] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewMode, setPreviewMode] = useState(true);
  const [archiveExporting, setArchiveExporting] = useState(false);
  const [archiveImportOpen, setArchiveImportOpen] = useState(false);
  const [archiveImportMode, setArchiveImportMode] = useState<
    "merge" | "replace"
  >("merge");
  const [pendingArchive, setPendingArchive] = useState<File | null>(null);
  const [archiveImporting, setArchiveImporting] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<TreeKey | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const [fileActionKey, setFileActionKey] = useState<string | null>(null);
  const [mobilePane, setMobilePane] = useState<"tree" | "viewer">("tree");
  const [dirEntries, setDirEntries] = useState<FileInfo[]>([]);
  const [dirLoading, setDirLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createKind, setCreateKind] = useState<CreateKind>("file");
  const [createParent, setCreateParent] = useState("/");
  const [createName, setCreateName] = useState("");
  const [createSaving, setCreateSaving] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([
    workspaceRootKey(),
  ]);
  const [treeCollapsed, setTreeCollapsed] = useState(() => {
    try {
      return localStorage.getItem(TREE_COLLAPSED_KEY) === "1";
    } catch {
      return false;
    }
  });

  const rootLabel = t("workspace.root", "工作区");

  const toggleTreeCollapsed = useCallback(() => {
    setTreeCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(TREE_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const { size: treeWidth, onResizeStart } = useHorizontalResize({
    min: 180,
    max: 420,
    defaultSize: 240,
    storageKey: "octop:workspace-drawer-tree-width",
  });

  const buildWorkspaceRootNode = useCallback(
    (children: TreeDataNode[]): TreeDataNode => ({
      key: workspaceRootKey(),
      title: (
        <span className={styles.treeNodeTitle}>
          <Folder size={13} className={styles.treeFileIcon} aria-hidden />
          <span className={styles.treeNodeName}>{rootLabel}</span>
        </span>
      ),
      isLeaf: false,
      children,
    }),
    [rootLabel],
  );

  const refreshRoot = useCallback(
    async (opts?: { activateRoot?: boolean }) => {
      if (!agentId || !workspaceReady) return;
      setTreeLoading(true);
      try {
        const data = await request<FileInfo[]>(
          withFromWorkspace(`/agents/${agentId}/workspace/tree?path=/`),
        );
        setTreeData([buildWorkspaceRootNode(toTreeNodes(data))]);
        setExpandedKeys([workspaceRootKey()]);
        if (opts?.activateRoot) {
          setSelectedKey(workspaceRootKey());
          setEditMode(false);
          setPreviewMode(false);
          setContent("");
          setDirEntries(data);
          setDirLoading(false);
          if (isMobile) setMobilePane("viewer");
        }
      } catch (err: unknown) {
        message.error(
          (err instanceof Error ? err.message : String(err)) ||
            t("workspace.refreshFailed", "刷新失败"),
        );
      } finally {
        setTreeLoading(false);
      }
    },
    [agentId, workspaceReady, t, buildWorkspaceRootNode, isMobile],
  );

  useEffect(() => {
    if (!open) return;
    setTreeData([]);
    setSelectedKey(null);
    setContent("");
    setEditMode(false);
    setMobilePane("tree");
    setDirEntries([]);
    if (agentId && workspaceReady) void refreshRoot({ activateRoot: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, agentId, workspaceReady]);

  const onLoadData = async (node: TreeDataNode): Promise<void> => {
    if (!agentId || !workspaceReady) return;
    const { path, is_dir } = pathFromKey(String(node.key));
    if (!is_dir) return;
    try {
      const data = await request<FileInfo[]>(
        withFromWorkspace(
          `/agents/${agentId}/workspace/tree?path=${encodeURIComponent(path)}`,
        ),
      );
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
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.loadChildrenFailed", "加载子目录失败"),
      );
    }
  };

  const reloadBranch = useCallback(
    async (dirPath: string) => {
      if (!agentId || !workspaceReady) return;
      if (isWorkspaceRoot(dirPath)) {
        await refreshRoot();
        return;
      }
      const dirKey = nodeKey({ path: dirPath, is_dir: true });
      try {
        const data = await request<FileInfo[]>(
          withFromWorkspace(
            `/agents/${agentId}/workspace/tree?path=${encodeURIComponent(
              dirPath,
            )}`,
          ),
        );
        const children = toTreeNodes(data);
        const replace = (nodes: TreeDataNode[]): TreeDataNode[] =>
          nodes.map((n) =>
            n.key === dirKey
              ? { ...n, children }
              : n.children
              ? { ...n, children: replace(n.children) }
              : n,
          );
        setTreeData((d) => replace(d));
      } catch (err: unknown) {
        message.error(
          (err instanceof Error ? err.message : String(err)) ||
            t("workspace.loadChildrenFailed", "加载子目录失败"),
        );
      }
    },
    [agentId, workspaceReady, t, refreshRoot],
  );

  const loadDirEntries = useCallback(
    async (dirPath: string) => {
      if (!agentId || !workspaceReady) return;
      setDirLoading(true);
      try {
        const data = await request<FileInfo[]>(
          withFromWorkspace(
            `/agents/${agentId}/workspace/tree?path=${encodeURIComponent(
              dirPath,
            )}`,
          ),
        );
        setDirEntries(data);
      } catch (err: unknown) {
        message.error(
          (err instanceof Error ? err.message : String(err)) ||
            t("workspace.loadChildrenFailed", "加载子目录失败"),
        );
        setDirEntries([]);
      } finally {
        setDirLoading(false);
      }
    },
    [agentId, workspaceReady, t],
  );

  const handleDelete = async (target: TreeKey) => {
    if (!agentId || !canDeletePath(target.path)) return;
    setFileActionKey(nodeKey(target));
    try {
      await workspaceApi.deleteWorkspaceFile(agentId, target.path);
      message.success(t("workspace.deleteSuccess"));
      if (selectedKey === nodeKey(target)) {
        setSelectedKey(null);
        setContent("");
        setDirEntries([]);
      }
      await reloadBranch(parentDir(target.path));
      const parent = parentDir(target.path);
      if (
        selectedKey === nodeKey({ path: parent, is_dir: true }) &&
        pathFromKey(selectedKey).is_dir
      ) {
        await loadDirEntries(parent);
      }
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.deleteFailed"),
      );
    } finally {
      setFileActionKey(null);
    }
  };

  const openCreate = (kind: CreateKind, parentPath: string) => {
    setCreateKind(kind);
    setCreateParent(parentPath);
    setCreateName("");
    setCreateOpen(true);
  };

  const confirmCreate = async () => {
    if (!agentId || !createName.trim()) return;
    const name = createName.trim();
    if (
      name.includes("/") ||
      name.includes("\\") ||
      name === "." ||
      name === ".."
    ) {
      message.warning(t("workspace.createFailed"));
      return;
    }
    const dest = joinPath(createParent, name);
    if (isProtectedPath(dest)) {
      message.warning(t("workspace.protectedPath"));
      return;
    }
    setCreateSaving(true);
    try {
      if (createKind === "folder") {
        await workspaceApi.mkdirWorkspaceDir(agentId, dest);
        message.success(t("workspace.createFolderSuccess"));
      } else {
        await workspaceApi.createWorkspaceFile(agentId, dest, "");
        message.success(t("workspace.createFileSuccess"));
      }
      setCreateOpen(false);
      await reloadBranch(createParent);
      const key = nodeKey({ path: dest, is_dir: createKind === "folder" });
      setSelectedKey(key);
      if (createKind === "folder") {
        void loadDirEntries(dest);
        if (isMobile) setMobilePane("viewer");
      } else {
        setDirEntries([]);
        setEditMode(false);
        setContent("");
        if (isMobile) setMobilePane("viewer");
        if (!getMediaKind(dest) && isProbablyText(dest)) {
          setFileLoading(true);
          try {
            const r = await request<{ content: string }>(
              withFromWorkspace(
                `/agents/${agentId}/workspace/file?path=${encodeURIComponent(
                  dest,
                )}`,
              ),
            );
            setContent(r.content);
          } finally {
            setFileLoading(false);
          }
        }
      }
    } catch (err: unknown) {
      message.error(
        err instanceof Error ? err.message : t("workspace.createFailed"),
      );
    } finally {
      setCreateSaving(false);
    }
  };

  const openRename = (target: TreeKey) => {
    const basename =
      target.path.split("/").filter(Boolean).pop() || target.path;
    setRenameTarget(target);
    setRenameValue(basename);
    setRenameOpen(true);
  };

  const confirmRename = async () => {
    if (!agentId || !renameTarget || !renameValue.trim()) return;
    const parent = parentDir(renameTarget.path);
    const dest = joinPath(parent, renameValue.trim());
    if (dest === renameTarget.path) {
      setRenameOpen(false);
      return;
    }
    setRenameSaving(true);
    try {
      const result = await workspaceApi.moveWorkspaceFile(
        agentId,
        renameTarget.path,
        dest,
      );
      message.success(t("workspace.renameSuccess"));
      setRenameOpen(false);
      if (selectedKey === nodeKey(renameTarget)) {
        setSelectedKey(nodeKey({ ...renameTarget, path: result.path }));
      }
      await reloadBranch(parent);
      if (parent !== parentDir(result.path)) {
        await reloadBranch(parentDir(result.path));
      }
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.renameFailed"),
      );
    } finally {
      setRenameSaving(false);
    }
  };

  const onDrop: TreeProps["onDrop"] = async (info) => {
    if (!agentId) return;
    const drag = pathFromKey(String(info.dragNode.key));
    const drop = pathFromKey(String(info.node.key));
    if (isProtectedPath(drag.path) || isProtectedPath(drop.path)) {
      message.warning(t("workspace.protectedPath"));
      return;
    }
    if (info.dropPosition !== 0 || !drop.is_dir) {
      message.warning(t("workspace.cannotMoveHere"));
      return;
    }
    if (isDescendantPath(drag.path, drop.path)) {
      message.warning(t("workspace.cannotMoveHere"));
      return;
    }
    const basename = drag.path.split("/").filter(Boolean).pop();
    if (!basename) return;
    const dest = joinPath(drop.path, basename);
    if (dest === drag.path) return;
    try {
      await workspaceApi.moveWorkspaceFile(agentId, drag.path, dest);
      message.success(t("workspace.moveSuccess"));
      if (selectedKey === nodeKey(drag)) {
        setSelectedKey(nodeKey({ ...drag, path: dest }));
      }
      await reloadBranch(parentDir(drag.path));
      await reloadBranch(drop.path);
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.moveFailed"),
      );
    }
  };

  const renderTreeTitle: TreeProps["titleRender"] = (node) => {
    const target = pathFromKey(String(node.key));
    const fname = isWorkspaceRoot(target.path)
      ? rootLabel
      : target.path.split("/").filter(Boolean).pop() || target.path;
    const actionKey = nodeKey(target);
    const menuItems = !canCreateIn(target.path)
      ? []
      : [
          ...(target.is_dir
            ? [
                {
                  key: "new-file",
                  label: t("workspace.createFile"),
                  onClick: () => openCreate("file", target.path),
                },
                {
                  key: "new-folder",
                  label: t("workspace.createFolder"),
                  onClick: () => openCreate("folder", target.path),
                },
              ]
            : []),
          ...(canDeletePath(target.path)
            ? [
                {
                  key: "rename",
                  label: t("workspace.rename"),
                  onClick: () => openRename(target),
                },
                {
                  key: "delete",
                  label: t("common.delete"),
                  danger: true,
                  onClick: () => {
                    Modal.confirm({
                      title: target.is_dir
                        ? t("workspace.deleteDirConfirm")
                        : t("workspace.deleteConfirm"),
                      okText: t("common.delete"),
                      cancelText: t("common.cancel"),
                      okButtonProps: { danger: true },
                      onOk: () => handleDelete(target),
                    });
                  },
                },
              ]
            : []),
        ];

    return (
      <span className={styles.treeNodeTitle}>
        {target.is_dir ? (
          <Folder size={13} className={styles.treeFileIcon} aria-hidden />
        ) : (
          <span className={styles.treeFileIcon}>
            {fileTreeIcon(target.path)}
          </span>
        )}
        <span className={styles.treeNodeName}>{fname}</span>
        {menuItems.length > 0 && (
          <Dropdown
            menu={{ items: menuItems }}
            trigger={["click"]}
            disabled={fileActionKey === actionKey}
          >
            <button
              type="button"
              className={styles.treeNodeMenu}
              aria-label={t("common.more")}
              onClick={(e) => e.stopPropagation()}
            >
              <MoreHorizontal size={14} />
            </button>
          </Dropdown>
        )}
      </span>
    );
  };

  const activateSelection = async (key: string) => {
    if (!agentId) return;
    const { path, is_dir } = pathFromKey(key);
    setSelectedKey(key);
    setEditMode(false);
    setPreviewMode(is_dir ? false : defaultPreviewMode(path));
    setContent("");
    if (is_dir) {
      setDirEntries([]);
      if (isMobile) setMobilePane("viewer");
      await loadDirEntries(path);
      return;
    }
    setDirEntries([]);
    if (isMobile) setMobilePane("viewer");
    if (getMediaKind(path)) return;
    if (!isProbablyText(path)) return;
    setFileLoading(true);
    try {
      const r = await request<{ content: string }>(
        withFromWorkspace(
          `/agents/${agentId}/workspace/file?path=${encodeURIComponent(path)}`,
        ),
      );
      setContent(r.content);
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.readFailed", "读取失败"),
      );
    } finally {
      setFileLoading(false);
    }
  };

  const onSelect = async (keys: React.Key[]) => {
    if (!keys.length) return;
    await activateSelection(String(keys[0]));
  };

  const selectDirEntry = async (info: FileInfo) => {
    const fullPath = workspaceEntryPath(info.path);
    await activateSelection(nodeKey({ path: fullPath, is_dir: !!info.is_dir }));
  };

  const navigateToDir = async (dirPath: string) => {
    setExpandedKeys(expandedKeysForDir(dirPath));
    await activateSelection(nodeKey({ path: dirPath, is_dir: true }));
  };

  const renderPathNav = (path: string, isDir: boolean) => {
    const segments = buildBreadcrumbSegments(path, rootLabel, isDir);
    return (
      <nav
        className={styles.pathBreadcrumb}
        aria-label={t("workspace.pathBreadcrumb", "路径导航")}
      >
        {segments.map((seg, index) => {
          const isLast = index === segments.length - 1;
          const clickable = seg.isDir && !(isLast && !isDir);
          return (
            <span
              key={`${seg.path}:${index}`}
              className={styles.pathBreadcrumbSegment}
            >
              {index > 0 && (
                <span className={styles.pathBreadcrumbSep} aria-hidden>
                  /
                </span>
              )}
              {clickable ? (
                <button
                  type="button"
                  className={styles.pathBreadcrumbLink}
                  onClick={() => void navigateToDir(seg.path)}
                  title={seg.label}
                >
                  {seg.label}
                </button>
              ) : (
                <span
                  className={styles.pathBreadcrumbCurrent}
                  title={seg.label}
                >
                  {seg.label}
                </span>
              )}
            </span>
          );
        })}
      </nav>
    );
  };

  const renderSplitDivider = () => (
    <div
      data-split-divider=""
      className={`${styles.splitDivider} ${
        treeCollapsed ? styles.splitDividerCollapsed : ""
      }`}
    >
      {!treeCollapsed && (
        <div
          className={styles.resizeHandle}
          role="separator"
          aria-orientation="vertical"
          aria-label={t("workspace.resizeTree", "调整目录宽度")}
          onPointerDown={onResizeStart}
        />
      )}
      <Tooltip
        title={
          treeCollapsed
            ? t("workspace.showTree", "显示目录树")
            : t("workspace.hideTree", "收起目录树")
        }
      >
        <button
          type="button"
          className={styles.splitToggleBtn}
          onClick={(e) => {
            e.stopPropagation();
            toggleTreeCollapsed();
          }}
          onMouseDown={(e) => e.stopPropagation()}
          aria-label={
            treeCollapsed
              ? t("workspace.showTree", "显示目录树")
              : t("workspace.hideTree", "收起目录树")
          }
        >
          {treeCollapsed ? (
            <ChevronRight size={14} strokeWidth={2} />
          ) : (
            <ChevronLeft size={14} strokeWidth={2} />
          )}
        </button>
      </Tooltip>
    </div>
  );

  const save = async () => {
    if (!agentId || !selectedKey) return;
    const { path } = pathFromKey(selectedKey);
    setSaving(true);
    try {
      await request(
        withFromWorkspace(
          `/agents/${agentId}/workspace/file?path=${encodeURIComponent(path)}`,
        ),
        {
          method: "PUT",
          body: JSON.stringify({ content }),
        },
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
    if (!agentId || !selectedKey) return;
    const { path } = pathFromKey(selectedKey);
    try {
      const blob = await requestBlob(
        withFromWorkspace(
          `/agents/${agentId}/workspace/download?path=${encodeURIComponent(
            path,
          )}`,
        ),
      );
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = path.split("/").pop() || "download";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.downloadFailed", "下载失败"),
      );
    }
  };

  const upload = async (file: File) => {
    if (!agentId) return false;
    const fd = new FormData();
    fd.append("file", file);
    const uploadDir = selected?.is_dir
      ? selected.path
      : selected && !selected.is_dir
      ? parentDir(selected.path)
      : WORKSPACE_ROOT_PATH;
    const uploadPath = joinPath(uploadDir, file.name);
    const url = withFromWorkspace(
      `/agents/${agentId}/workspace/upload?path=${encodeURIComponent(
        uploadPath,
      )}`,
    );
    try {
      await requestUpload(url, fd);
      message.success(
        t("workspace.uploaded", {
          name: file.name,
          defaultValue: `已上传 ${file.name}`,
        }),
      );
      await reloadBranch(uploadDir);
      if (selectedKey === nodeKey({ path: uploadDir, is_dir: true })) {
        await loadDirEntries(uploadDir);
      }
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.uploadFailed", "上传失败"),
      );
    }
    return false;
  };

  const exportArchive = async () => {
    setArchiveExporting(true);
    try {
      const blob = await workspaceApi.downloadWorkspaceArchive(agentId);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `workspace-${agentId}.zip`;
      a.click();
      URL.revokeObjectURL(a.href);
      message.success(t("workspace.archiveExportSuccess"));
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.archiveExportFailed"),
      );
    } finally {
      setArchiveExporting(false);
    }
  };

  const confirmArchiveImport = async () => {
    if (!pendingArchive) return;
    setArchiveImporting(true);
    try {
      const result = await workspaceApi.importWorkspaceArchive(
        agentId,
        pendingArchive,
        archiveImportMode,
      );
      message.success(
        t("workspace.archiveImportSuccess", { count: result.imported }),
      );
      if (result.warnings?.length) message.warning(result.warnings.join(" "));
      setArchiveImportOpen(false);
      setPendingArchive(null);
      void refreshRoot();
    } catch (err: unknown) {
      message.error(
        (err instanceof Error ? err.message : String(err)) ||
          t("workspace.archiveImportFailed"),
      );
    } finally {
      setArchiveImporting(false);
    }
  };

  const selected = selectedKey ? pathFromKey(selectedKey) : null;
  const previewKind =
    selected && !selected.is_dir ? getPreviewKind(selected.path) : null;
  const docKind =
    selected && !selected.is_dir ? getDocKind(selected.path) : null;
  const showEditButton =
    selected && !selected.is_dir && isProbablyText(selected.path);
  const showPreviewToggle = previewKind !== null && !editMode && content !== "";

  const drawerTitle = (
    <div className={styles.drawerTitleRow}>
      <span className={styles.drawerTitleText}>
        {t("pageShell.workspace.title")}
      </span>
      <Space size={isMobile ? 4 : 8} className={styles.drawerTitleActions}>
        <Tooltip
          title={
            isMobile
              ? t("common.refresh")
              : t(
                  "workspace.refreshHint",
                  "只刷新根目录；子目录在展开时按需加载",
                )
          }
        >
          <Button
            size="small"
            icon={<RefreshCw size={13} />}
            onClick={() => void refreshRoot()}
            aria-label={t("common.refresh")}
          >
            {isMobile ? null : t("common.refresh")}
          </Button>
        </Tooltip>
        <Tooltip title={t("workspace.exportArchive")}>
          <Button
            size="small"
            icon={<Download size={13} />}
            loading={archiveExporting}
            onClick={() => void exportArchive()}
            aria-label={t("workspace.exportArchive")}
          >
            {isMobile ? null : t("workspace.exportArchive")}
          </Button>
        </Tooltip>
        <Upload
          accept=".zip,application/zip"
          showUploadList={false}
          beforeUpload={(file) => {
            setPendingArchive(file);
            setArchiveImportOpen(true);
            return false;
          }}
        >
          <Tooltip title={t("workspace.importArchive")}>
            <Button
              size="small"
              icon={<Archive size={13} />}
              aria-label={t("workspace.importArchive")}
            >
              {isMobile ? null : t("workspace.importArchive")}
            </Button>
          </Tooltip>
        </Upload>
        <Upload showUploadList={false} beforeUpload={upload} multiple={false}>
          <Tooltip title={t("common.upload")}>
            <Button
              size="small"
              icon={<UploadIcon size={13} />}
              aria-label={t("common.upload")}
            >
              {isMobile ? null : t("common.upload")}
            </Button>
          </Tooltip>
        </Upload>
      </Space>
    </div>
  );

  return (
    <Drawer
      title={drawerTitle}
      open={open}
      onClose={onClose}
      width={isMobile ? "100%" : "80vw"}
      styles={{
        body: {
          padding: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        },
      }}
      destroyOnClose
    >
      <Modal
        title={t("workspace.archiveImportTitle")}
        open={archiveImportOpen}
        onCancel={() => {
          if (!archiveImporting) {
            setArchiveImportOpen(false);
            setPendingArchive(null);
          }
        }}
        onOk={() => void confirmArchiveImport()}
        okText={t("workspace.archiveImportConfirm")}
        cancelText={t("common.cancel")}
        confirmLoading={archiveImporting}
        okButtonProps={{ danger: archiveImportMode === "replace" }}
      >
        <p>
          {t("workspace.archiveImportBody", {
            name: pendingArchive?.name ?? "",
          })}
        </p>
        <Radio.Group
          value={archiveImportMode}
          onChange={(e) => setArchiveImportMode(e.target.value)}
          style={{ display: "flex", flexDirection: "column", gap: 8 }}
        >
          <Radio value="merge">{t("workspace.archiveModeMerge")}</Radio>
          <Radio value="replace">{t("workspace.archiveModeReplace")}</Radio>
        </Radio.Group>
      </Modal>

      <Modal
        title={
          createKind === "folder"
            ? t("workspace.createFolder")
            : t("workspace.createFile")
        }
        open={createOpen}
        onCancel={() => {
          if (!createSaving) setCreateOpen(false);
        }}
        onOk={() => void confirmCreate()}
        okText={t("common.create")}
        cancelText={t("common.cancel")}
        confirmLoading={createSaving}
      >
        <Input
          value={createName}
          onChange={(e) => setCreateName(e.target.value)}
          onPressEnter={() => void confirmCreate()}
          placeholder={
            createKind === "folder"
              ? t("workspace.newFolderName")
              : t("workspace.newFileName")
          }
          autoFocus
        />
      </Modal>

      <Modal
        title={t("workspace.rename")}
        open={renameOpen}
        onCancel={() => {
          if (!renameSaving) setRenameOpen(false);
        }}
        onOk={() => void confirmRename()}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
        confirmLoading={renameSaving}
      >
        <Input
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onPressEnter={() => void confirmRename()}
          autoFocus
        />
      </Modal>

      {!workspaceReady ? (
        <div style={{ padding: 24 }}>
          <AgentNotReadyScreen agent={activeAgent} />
        </div>
      ) : (
        <div
          className={`${styles.split} ${isMobile ? styles.splitMobile : ""}`}
          style={{ flex: 1, minHeight: 0 }}
        >
          {((!isMobile && !treeCollapsed) ||
            (isMobile && mobilePane === "tree")) && (
            <div
              className={styles.treePane}
              style={isMobile ? undefined : { width: treeWidth }}
            >
              <div className={styles.treeScroll}>
                {treeLoading ? (
                  <div className={styles.viewerLoading}>
                    <Spin />
                  </div>
                ) : (
                  <Tree
                    treeData={treeData}
                    loadData={onLoadData}
                    onSelect={(keys) => void onSelect(keys)}
                    selectedKeys={selectedKey ? [selectedKey] : []}
                    expandedKeys={expandedKeys}
                    onExpand={(keys) => setExpandedKeys(keys as string[])}
                    blockNode
                    draggable={{ icon: false }}
                    onDrop={(info) => void onDrop(info)}
                    titleRender={renderTreeTitle}
                  />
                )}
              </div>
            </div>
          )}

          {!isMobile && renderSplitDivider()}

          {(!isMobile || mobilePane === "viewer") && (
            <div
              className={`${styles.viewerPane} ${
                !isMobile && treeCollapsed ? styles.viewerPaneFull : ""
              }`}
            >
              {!selected ? (
                <div className={styles.viewerEmpty}>
                  <Empty
                    description={t(
                      "workspace.pickEntry",
                      "选择工作区或文件以查看内容",
                    )}
                  />
                </div>
              ) : selected.is_dir ? (
                <>
                  <div className={styles.viewerHeader}>
                    {isMobile && (
                      <button
                        type="button"
                        className={styles.mobileBackBtn}
                        onClick={() => setMobilePane("tree")}
                        aria-label={t("common.back", "返回")}
                      >
                        <ChevronLeft size={18} />
                      </button>
                    )}
                    <div className={styles.viewerPathRow}>
                      {renderPathNav(selected.path, true)}
                    </div>
                    <div className={styles.toolbar}>
                      {canCreateIn(selected.path) && (
                        <>
                          <Tooltip title={t("workspace.createFile")}>
                            <button
                              type="button"
                              className={styles.toolBtnIcon}
                              onClick={() => openCreate("file", selected.path)}
                              aria-label={t("workspace.createFile")}
                            >
                              <FilePlus size={16} strokeWidth={2} />
                            </button>
                          </Tooltip>
                          <Tooltip title={t("workspace.createFolder")}>
                            <button
                              type="button"
                              className={styles.toolBtnIcon}
                              onClick={() =>
                                openCreate("folder", selected.path)
                              }
                              aria-label={t("workspace.createFolder")}
                            >
                              <FolderPlus size={16} strokeWidth={2} />
                            </button>
                          </Tooltip>
                          <Tooltip title={t("common.refresh")}>
                            <button
                              type="button"
                              className={styles.toolBtnIcon}
                              onClick={() => void loadDirEntries(selected.path)}
                              aria-label={t("common.refresh")}
                            >
                              <RefreshCw size={16} strokeWidth={2} />
                            </button>
                          </Tooltip>
                          {canDeletePath(selected.path) && (
                            <Popconfirm
                              title={t("workspace.deleteDirConfirm")}
                              onConfirm={() => void handleDelete(selected)}
                              okText={t("common.delete")}
                              cancelText={t("common.cancel")}
                            >
                              <button
                                type="button"
                                className={styles.toolBtnIcon}
                                title={t("common.delete")}
                                aria-label={t("common.delete")}
                              >
                                <Trash2 size={16} strokeWidth={2} />
                              </button>
                            </Popconfirm>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                  <div className={styles.viewerBody}>
                    {dirLoading ? (
                      <div className={styles.viewerLoading}>
                        <Spin />
                      </div>
                    ) : dirEntries.length === 0 ? (
                      <div className={styles.viewerEmpty}>
                        <Empty description={t("workspace.dirListingEmpty")} />
                      </div>
                    ) : (
                      <div className={styles.dirListing}>
                        <div className={styles.dirListingHead}>
                          <span>{t("workspace.dirColName")}</span>
                          <span>{t("workspace.dirColType")}</span>
                          <span>{t("workspace.dirColSize")}</span>
                          <span>{t("workspace.dirColModified")}</span>
                        </div>
                        {sortFileInfos(dirEntries).map((entry) => {
                          const fullPath = workspaceEntryPath(entry.path);
                          const name =
                            fullPath.split("/").filter(Boolean).pop() ||
                            fullPath;
                          return (
                            <button
                              key={fullPath}
                              type="button"
                              className={styles.dirListingRow}
                              onClick={() => void selectDirEntry(entry)}
                            >
                              <span className={styles.dirListingName}>
                                {entry.is_dir ? (
                                  <Folder
                                    size={14}
                                    className={styles.dirListingIcon}
                                  />
                                ) : (
                                  <span className={styles.dirListingIcon}>
                                    {fileTreeIcon(fullPath)}
                                  </span>
                                )}
                                <span>{name}</span>
                              </span>
                              <span className={styles.dirListingMeta}>
                                {entry.is_dir
                                  ? t("workspace.dirTypeFolder")
                                  : t("workspace.dirTypeFile")}
                              </span>
                              <span className={styles.dirListingMeta}>
                                {entry.is_dir || entry.size == null
                                  ? "—"
                                  : formatSize(entry.size)}
                              </span>
                              <span className={styles.dirListingMeta}>
                                {formatModified(entry.modified_at, timeZone)}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <div className={styles.viewerHeader}>
                    {isMobile && (
                      <button
                        type="button"
                        className={styles.mobileBackBtn}
                        onClick={() => setMobilePane("tree")}
                        aria-label={t("common.back", "返回")}
                      >
                        <ChevronLeft size={18} />
                      </button>
                    )}
                    <div className={styles.viewerPathRow}>
                      {renderPathNav(selected.path, false)}
                    </div>
                    <div className={styles.toolbar}>
                      {showPreviewToggle && (
                        <Segmented
                          size="small"
                          value={previewMode ? "preview" : "source"}
                          options={[
                            { label: t("common.preview"), value: "preview" },
                            {
                              label: t("workspace.source", "源码"),
                              value: "source",
                            },
                          ]}
                          onChange={(v) => setPreviewMode(v === "preview")}
                        />
                      )}
                      <button
                        type="button"
                        className={styles.toolBtnIcon}
                        onClick={() => void download()}
                        title={t("common.download")}
                        aria-label={t("common.download")}
                      >
                        <ArrowDownToLine size={16} strokeWidth={2} />
                      </button>
                      {selected && canDeletePath(selected.path) && (
                        <Popconfirm
                          title={
                            selected.is_dir
                              ? t("workspace.deleteDirConfirm")
                              : t("workspace.deleteConfirm")
                          }
                          onConfirm={() => void handleDelete(selected)}
                          okText={t("common.delete")}
                          cancelText={t("common.cancel")}
                        >
                          <button
                            type="button"
                            className={styles.toolBtnIcon}
                            title={t("common.delete")}
                            aria-label={t("common.delete")}
                          >
                            <Trash2 size={16} strokeWidth={2} />
                          </button>
                        </Popconfirm>
                      )}
                      {showEditButton &&
                        (editMode ? (
                          <button
                            type="button"
                            className={styles.toolBtnPrimary}
                            onClick={() => void save()}
                            disabled={saving}
                          >
                            <Save size={14} />
                            {saving
                              ? t("workspace.saving", "保存中…")
                              : t("common.save")}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className={styles.toolBtn}
                            onClick={() => setEditMode(true)}
                          >
                            <Pencil size={14} />
                            {t("common.edit")}
                          </button>
                        ))}
                    </div>
                  </div>
                  <div
                    className={styles.viewerBody}
                    style={
                      (showEditButton && editMode) ||
                      docKind !== null ||
                      (previewMode && previewNeedsFillLayout(previewKind))
                        ? {
                            overflow: "hidden",
                            display: "flex",
                            flexDirection: "column",
                          }
                        : undefined
                    }
                  >
                    <FileViewer
                      agentId={agentId}
                      path={selected.path}
                      editMode={editMode}
                      value={content}
                      onChange={setContent}
                      fileLoading={fileLoading}
                      previewMode={previewMode}
                    />
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}
