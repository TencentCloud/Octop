import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type SyntheticEvent,
} from "react";
import { Input, Spin, TreeSelect } from "antd";
import type { TreeSelectProps } from "antd";
import { FolderPlus, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { request } from "../../../api/request";
import {
  HOST_FS_ROOT,
  ancestorDirPaths,
  appendChildren,
  insertChild,
  makeRootNode,
  normalizeTreeRoot,
  renameNode,
  sanitizeTree,
  type DirTreeNode,
} from "./rootDirTree";
import styles from "./RootDirSelect.module.less";

interface DirEntry {
  path: string;
  name: string;
}

interface RootDirSelectProps {
  value?: string;
  onChange?: (value: string) => void;
  /** Tree browse root: host ``/`` (or drive root). Default value is still home. */
  treeRoot?: string;
  /** When true, shows the current path but blocks picking / mkdir / rename. */
  disabled?: boolean;
}

type DisplayTreeNode = Omit<DirTreeNode, "title" | "children"> & {
  title: ReactNode;
  children?: DisplayTreeNode[];
};

function stopRowEvent(e: SyntheticEvent) {
  e.preventDefault();
  e.stopPropagation();
}

function mapDisplayTitles(
  nodes: DirTreeNode[],
  renderTitle: (node: DirTreeNode) => ReactNode,
): DisplayTreeNode[] {
  return nodes.map((node) => ({
    ...node,
    title: renderTitle(node),
    children: node.children
      ? mapDisplayTitles(node.children, renderTitle)
      : undefined,
  }));
}

function entriesToNodes(entries: DirEntry[]): DirTreeNode[] {
  return entries.map((entry) => ({
    value: entry.path,
    title: entry.name,
    isLeaf: false,
  }));
}

export default function RootDirSelect({
  value,
  onChange,
  treeRoot = HOST_FS_ROOT,
  disabled = false,
}: RootDirSelectProps) {
  const { t } = useTranslation();
  const normalizedRoot = normalizeTreeRoot(treeRoot);
  const [treeData, setTreeData] = useState<DirTreeNode[]>(() => [
    makeRootNode(normalizedRoot),
  ]);
  const [expandedKeys, setExpandedKeys] = useState<string[] | undefined>(
    undefined,
  );
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const editingPathRef = useRef<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  /** Ant Design ``treeLoadedKeys`` (array); membership checks use the Set ref. */
  const [loadedKeys, setLoadedKeys] = useState<string[]>([]);
  const loadedKeysRef = useRef(new Set<string>());
  const loadingPathsRef = useRef(new Set<string>());

  const withSanitizedTree = useCallback(
    (
      updater: (prev: DirTreeNode[]) => DirTreeNode[],
    ): ((prev: DirTreeNode[]) => DirTreeNode[]) => {
      return (prev) => sanitizeTree(updater(prev), normalizedRoot);
    },
    [normalizedRoot],
  );

  const markLoaded = useCallback((paths: string[]) => {
    let changed = false;
    for (const path of paths) {
      if (!loadedKeysRef.current.has(path)) {
        loadedKeysRef.current.add(path);
        changed = true;
      }
    }
    if (changed) {
      setLoadedKeys([...loadedKeysRef.current]);
    }
  }, []);

  const resetTree = useCallback(() => {
    setTreeData([makeRootNode(normalizedRoot)]);
    loadedKeysRef.current.clear();
    setLoadedKeys([]);
    setExpandedKeys(undefined);
    loadingPathsRef.current.clear();
  }, [normalizedRoot]);

  useEffect(() => {
    resetTree();
  }, [resetTree]);

  /** Lazy-load one directory (TreeSelect ``loadData`` / ancestor prefetch). */
  const loadDirChildren = useCallback(
    async (path: string, options?: { showError?: boolean }) => {
      const showError = options?.showError !== false;
      if (
        !path ||
        loadedKeysRef.current.has(path) ||
        loadingPathsRef.current.has(path)
      ) {
        return;
      }

      loadingPathsRef.current.add(path);
      try {
        const data = await request<{ entries: DirEntry[] }>(
          `/filesystem/dirs?path=${encodeURIComponent(path)}`,
        );
        setTreeData(
          withSanitizedTree((prev) =>
            appendChildren(prev, path, entriesToNodes(data.entries)),
          ),
        );
        markLoaded([path]);
      } catch {
        if (showError) {
          message.error(t("experts.rootDirListFailed"));
        }
      } finally {
        loadingPathsRef.current.delete(path);
      }
    },
    [markLoaded, t, withSanitizedTree],
  );
  const loadDirChildrenRef = useRef(loadDirChildren);
  loadDirChildrenRef.current = loadDirChildren;

  // Prefetch ancestors shallow→deep from the API, then expand. Expanding before
  // parents exist makes antd loadData miss child merges; no synthetic path chain.
  useEffect(() => {
    if (!value) return;
    const ancestors = ancestorDirPaths(value, normalizedRoot);
    if (ancestors.length === 0) return;

    let cancelled = false;
    void (async () => {
      for (const path of ancestors) {
        if (cancelled) return;
        await loadDirChildrenRef.current(path, { showError: false });
      }
      if (cancelled) return;
      setExpandedKeys((prev) => [...new Set([...(prev ?? []), ...ancestors])]);
    })();

    return () => {
      cancelled = true;
    };
  }, [value, normalizedRoot]);

  const loadData = useCallback<NonNullable<TreeSelectProps["loadData"]>>(
    async (node) => {
      await loadDirChildren(String(node.value ?? ""));
    },
    [loadDirChildren],
  );

  const beginEditing = useCallback((path: string, name: string) => {
    editingPathRef.current = path;
    setEditingPath(path);
    setEditingName(name);
    setOpen(true);
  }, []);

  const commitRename = useCallback(
    async (path: string, nextName: string) => {
      if (editingPathRef.current !== path) return;
      editingPathRef.current = null;
      setEditingPath(null);

      const trimmed = nextName.trim();
      const currentTitle = findNodeTitle(treeData, path) ?? trimmed;
      if (!trimmed || trimmed === currentTitle) {
        return;
      }
      setBusy(true);
      try {
        const result = await request<{ path: string; name: string }>(
          "/filesystem/rename",
          {
            method: "POST",
            body: JSON.stringify({ path, new_name: trimmed }),
          },
        );
        setTreeData(
          withSanitizedTree((prev) =>
            renameNode(prev, path, result.path, result.name),
          ),
        );
        if (loadedKeysRef.current.delete(path)) {
          loadedKeysRef.current.add(result.path);
          setLoadedKeys([...loadedKeysRef.current]);
        }
        if (value === path) {
          onChange?.(result.path);
        }
      } catch {
        message.error(t("experts.rootDirRenameFailed"));
        beginEditing(path, trimmed);
      } finally {
        setBusy(false);
      }
    },
    [beginEditing, onChange, t, treeData, value, withSanitizedTree],
  );

  const handleMkdir = useCallback(
    async (parentPath: string) => {
      if (busy) return;
      setBusy(true);
      try {
        const result = await request<{ path: string; name: string }>(
          "/filesystem/mkdir",
          {
            method: "POST",
            body: JSON.stringify({
              path: parentPath,
              base_name: t("experts.rootDirNewFolder"),
            }),
          },
        );
        setTreeData(
          withSanitizedTree((prev) =>
            insertChild(prev, parentPath, {
              value: result.path,
              title: result.name,
              isLeaf: false,
            }),
          ),
        );
        const ancestors = ancestorDirPaths(result.path, normalizedRoot);
        setExpandedKeys((prev) => [
          ...new Set([...(prev ?? []), ...ancestors]),
        ]);
        beginEditing(result.path, result.name);
      } catch {
        message.error(t("experts.rootDirMkdirFailed"));
      } finally {
        setBusy(false);
      }
    },
    [beginEditing, busy, normalizedRoot, t, withSanitizedTree],
  );

  const renderTitle = useCallback(
    (node: DirTreeNode) => {
      const path = String(node.value ?? "");
      const name =
        typeof node.title === "string" && node.title.length > 0
          ? node.title
          : path.split("/").filter(Boolean).pop() || path;

      if (editingPath === path) {
        return (
          <span
            className={styles.rootDirTitle}
            onClick={stopRowEvent}
            onMouseDown={stopRowEvent}
          >
            <Input
              size="small"
              autoFocus
              value={editingName}
              disabled={busy}
              data-testid="root-dir-rename-input"
              onChange={(e) => setEditingName(e.target.value)}
              onPressEnter={() => {
                void commitRename(path, editingName);
              }}
              onBlur={() => {
                void commitRename(path, editingName);
              }}
              style={{ width: 160 }}
            />
          </span>
        );
      }

      if (disabled) {
        return (
          <span className={styles.rootDirTitle}>
            <span className={styles.rootDirTitleLabel}>{name}</span>
          </span>
        );
      }

      return (
        <span className={styles.rootDirTitle}>
          <span className={styles.rootDirTitleLabel}>{name}</span>
          <span
            className={styles.rootDirActions}
            style={{
              display: "inline-flex",
              marginLeft: "auto",
              flexShrink: 0,
            }}
          >
            {path !== normalizedRoot ? (
              <button
                type="button"
                className={styles.rootDirActionBtn}
                title={t("experts.rootDirRename")}
                aria-label={t("experts.rootDirRename")}
                data-testid={`root-dir-rename-${path}`}
                disabled={busy}
                onClick={(e) => {
                  stopRowEvent(e);
                  beginEditing(path, name);
                }}
                onMouseDown={stopRowEvent}
              >
                <Pencil size={14} />
              </button>
            ) : null}
            <button
              type="button"
              className={styles.rootDirActionBtn}
              title={t("experts.rootDirMkdir")}
              aria-label={t("experts.rootDirMkdir")}
              data-testid={`root-dir-mkdir-${path}`}
              disabled={busy}
              onClick={(e) => {
                stopRowEvent(e);
                void handleMkdir(path);
              }}
              onMouseDown={stopRowEvent}
            >
              <FolderPlus size={14} />
            </button>
          </span>
        </span>
      );
    },
    [
      beginEditing,
      busy,
      commitRename,
      disabled,
      editingName,
      editingPath,
      handleMkdir,
      normalizedRoot,
      t,
    ],
  );

  // Bake row UI into `title`. Use treeNodeLabelProp=value so the input shows
  // the absolute path and never the action buttons (treeTitleRender would).
  const displayTreeData = useMemo(
    () => mapDisplayTitles(treeData, renderTitle),
    [treeData, renderTitle],
  );

  return (
    <TreeSelect
      className={styles.rootDirSelect}
      popupClassName={styles.rootDirDropdown}
      classNames={{ popup: { root: styles.rootDirDropdown } }}
      disabled={disabled}
      open={disabled ? false : open}
      onDropdownVisibleChange={(next) => {
        if (disabled) return;
        if (!next && editingPathRef.current) return;
        setOpen(next);
      }}
      value={value}
      onChange={(next) => {
        if (disabled) return;
        setOpen(false);
        onChange?.(next);
      }}
      treeData={displayTreeData}
      loadData={loadData}
      treeLoadedKeys={loadedKeys}
      virtual={false}
      treeNodeLabelProp="value"
      treeExpandedKeys={expandedKeys}
      onTreeExpand={(keys) => setExpandedKeys(keys.map(String))}
      showSearch
      treeLine
      treeDefaultExpandAll={false}
      placeholder={t("experts.backendRootDirPlaceholder")}
      notFoundContent={<Spin size="small" />}
      style={{ width: "100%" }}
      popupMatchSelectWidth
      dropdownStyle={{ maxHeight: 360 }}
      filterTreeNode={(input, node) => {
        const q = input.trim().toLowerCase();
        const path = String(node.value ?? "").toLowerCase();
        const base = path.split("/").filter(Boolean).pop() ?? "";
        return path.includes(q) || base.includes(q);
      }}
    />
  );
}

function findNodeTitle(nodes: DirTreeNode[], path: string): string | null {
  for (const node of nodes) {
    if (node.value === path) return node.title;
    if (node.children?.length) {
      const found = findNodeTitle(node.children, path);
      if (found != null) return found;
    }
  }
  return null;
}
