import { useCallback, useEffect, useState } from "react";
import { message, Spin, TreeSelect } from "antd";
import type { TreeSelectProps } from "antd";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";

interface DirEntry {
  path: string;
  name: string;
}

interface DirTreeNode {
  value: string;
  title: string;
  isLeaf?: boolean;
  children?: DirTreeNode[];
}

const ROOT_NODE: DirTreeNode = {
  value: "/",
  title: "/",
  isLeaf: false,
};

function appendChildren(
  nodes: DirTreeNode[],
  parentPath: string,
  children: DirTreeNode[],
): DirTreeNode[] {
  return nodes.map((node) => {
    if (node.value === parentPath) {
      const existing = node.children ?? [];
      const seen = new Set(existing.map((child) => child.value));
      const merged = [
        ...existing,
        ...children.filter((child) => !seen.has(child.value)),
      ];
      return { ...node, children: merged };
    }
    if (node.children?.length) {
      return {
        ...node,
        children: appendChildren(node.children, parentPath, children),
      };
    }
    return node;
  });
}

function ensurePathInTree(nodes: DirTreeNode[], path: string): DirTreeNode[] {
  if (!path || nodes.some((node) => node.value === path)) {
    return nodes;
  }
  return [...nodes, { value: path, title: path, isLeaf: false }];
}

interface RootDirSelectProps {
  value?: string;
  onChange?: (value: string) => void;
}

export default function RootDirSelect({ value, onChange }: RootDirSelectProps) {
  const { t } = useTranslation();
  const [treeData, setTreeData] = useState<DirTreeNode[]>([ROOT_NODE]);

  useEffect(() => {
    if (!value) return;
    setTreeData((prev) => ensurePathInTree(prev, value));
  }, [value]);

  const loadData = useCallback<NonNullable<TreeSelectProps["loadData"]>>(
    async (node) => {
      const path = String(node.value ?? "");
      if (!path) return;

      try {
        const data = await request<{ entries: DirEntry[] }>(
          `/filesystem/dirs?path=${encodeURIComponent(path)}`,
        );
        const children = data.entries.map((entry) => ({
          value: entry.path,
          title: entry.name,
          isLeaf: false,
        }));
        setTreeData((prev) => appendChildren(prev, path, children));
      } catch {
        message.error(t("experts.rootDirListFailed"));
      }
    },
    [t],
  );

  return (
    <TreeSelect
      value={value}
      onChange={onChange}
      treeData={treeData}
      loadData={loadData}
      showSearch
      treeLine
      treeDefaultExpandAll={false}
      placeholder={t("experts.backendRootDirPlaceholder")}
      notFoundContent={<Spin size="small" />}
      style={{ width: "100%" }}
      popupMatchSelectWidth={false}
      dropdownStyle={{ maxHeight: 360, overflow: "auto" }}
      filterTreeNode={(input, node) =>
        String(node.title ?? "")
          .toLowerCase()
          .includes(input.trim().toLowerCase()) ||
        String(node.value ?? "")
          .toLowerCase()
          .includes(input.trim().toLowerCase())
      }
    />
  );
}
