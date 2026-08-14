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
  ROOT_NODE,
  ancestorDirPaths,
  appendChildren,
  ensurePathInTree,
  insertChild,
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
}

type DisplayTreeNode = Omit<DirTreeNode, "title" | "children"> & {
  title: ReactNode;
  children?: DisplayTreeNode[];
};

function withSanitizedTree(
  updater: (prev: DirTreeNode[]) => DirTreeNode[],
): (prev: DirTreeNode[]) => DirTreeNode[] {
  return (prev) => sanitizeTree(updater(prev));
}

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

export default function RootDirSelect({ value, onChange }: RootDirSelectProps) {
  const { t } = useTranslation();
  const [treeData, setTreeData] = useState<DirTreeNode[]>([ROOT_NODE]);
  const [expandedKeys, setExpandedKeys] = useState<string[] | undefined>(
    undefined,
  );
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const editingPathRef = useRef<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [loadedKeys, setLoadedKeys] = useState<string[]>([]);
  const loadingPathsRef = useRef(new Set<string>());

  useEffect(() => {
    if (!value) return;
    setTreeData((prev) => sanitizeTree(ensurePathInTree(prev, value)));
  }, [value]);

  const loadData = useCallback<NonNullable<TreeSelectProps["loadData"]>>(
    async (node) => {
      const path = String(node.value ?? "");
      if (
        !path ||
        loadedKeys.includes(path) ||
        loadingPathsRef.current.has(path)
      ) {
        return;
      }

      loadingPathsRef.current.add(path);
      try {
        const data = await request<{ entries: DirEntry[] }>(
          `/filesystem/dirs?path=${encodeURIComponent(path)}`,
        );
        const children = data.entries.map((entry) => ({
          value: entry.path,
          title: entry.name,
          isLeaf: false,
        }));
        setTreeData(
          withSanitizedTree((prev) => appendChildren(prev, path, children)),
        );
        setLoadedKeys((prev) => (prev.includes(path) ? prev : [...prev, path]));
      } catch {
        message.error(t("experts.rootDirListFailed"));
      } finally {
        loadingPathsRef.current.delete(path);
      }
    },
    [loadedKeys, t],
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
        setLoadedKeys((prev) =>
          prev.map((key) => (key === path ? result.path : key)),
        );
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
    [beginEditing, onChange, t, treeData, value],
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
        const ancestors = ancestorDirPaths(result.path);
        setExpandedKeys((prev) => {
          const base = prev ?? [];
          return [...new Set([...base, ...ancestors])];
        });
        beginEditing(result.path, result.name);
      } catch {
        message.error(t("experts.rootDirMkdirFailed"));
      } finally {
        setBusy(false);
      }
    },
    [beginEditing, busy, t],
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
            {path !== "/" ? (
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
      editingName,
      editingPath,
      handleMkdir,
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
      open={open}
      onDropdownVisibleChange={(next) => {
        if (!next && editingPathRef.current) return;
        setOpen(next);
      }}
      value={value}
      onChange={(next) => {
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
