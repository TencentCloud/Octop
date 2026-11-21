import { useCallback, useEffect, useRef, useState } from "react";
import { Spin, TreeSelect } from "antd";
import { useTranslation } from "react-i18next";
import { request } from "../../../../api/request";
import { withFromWorkspace } from "../../../../utils/fromWorkspace";
import { message } from "@/utils/antdMessage";
import {
  insertScriptPathChildren,
  isScriptFile,
  scriptPathAncestors,
  scriptPathNodes,
  type ScriptPathNode,
  type WorkspaceTreeEntry,
} from "./scriptPathTree";

interface ScriptPathSelectProps {
  agentId: string | null;
  lang?: string;
  value?: string;
  onChange?: (value: string) => void;
}

async function loadDir(
  agentId: string,
  dir: string,
  lang: string,
): Promise<ScriptPathNode[]> {
  const apiPath = dir ? `/${dir}` : "/";
  const rows = await request<WorkspaceTreeEntry[]>(
    withFromWorkspace(
      `/agents/${agentId}/workspace/tree?path=${encodeURIComponent(apiPath)}`,
    ),
  );
  return scriptPathNodes(rows, lang);
}

export function ScriptPathSelect({
  agentId,
  lang = "python",
  value,
  onChange,
}: ScriptPathSelectProps) {
  const { t } = useTranslation();
  const [treeData, setTreeData] = useState<ScriptPathNode[]>([]);
  const [loading, setLoading] = useState(false);
  const loadedRef = useRef(new Set<string>());
  const loadingRef = useRef(new Set<string>());
  const generation = useRef(0);

  const reset = useCallback(() => {
    generation.current += 1;
    loadedRef.current.clear();
    loadingRef.current.clear();
    setTreeData([]);
  }, []);

  useEffect(() => {
    reset();
  }, [agentId, lang, reset]);

  useEffect(() => {
    if (value && !isScriptFile(value, lang)) onChange?.("");
  }, [lang, onChange, value]);

  const fetchDir = useCallback(
    async (dir: string) => {
      if (
        !agentId ||
        loadedRef.current.has(dir) ||
        loadingRef.current.has(dir)
      ) {
        return;
      }
      const gen = generation.current;
      loadingRef.current.add(dir);
      try {
        const children = await loadDir(agentId, dir, lang);
        if (gen !== generation.current) return;
        loadedRef.current.add(dir);
        setTreeData((prev) =>
          dir ? insertScriptPathChildren(prev, dir, children) : children,
        );
      } catch {
        if (gen !== generation.current) return;
        message.error(t("cronJobs.form.scriptPathLoadFailed"));
      } finally {
        if (gen === generation.current) loadingRef.current.delete(dir);
      }
    },
    [agentId, lang, t],
  );

  useEffect(() => {
    if (!agentId || !value) return;
    let cancelled = false;
    void (async () => {
      for (const dir of scriptPathAncestors(value)) {
        if (cancelled) return;
        await fetchDir(dir);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentId, fetchDir, value]);

  return (
    <TreeSelect
      style={{ width: "100%" }}
      value={value || undefined}
      disabled={!agentId}
      treeData={treeData}
      treeNodeLabelProp="label"
      placeholder={t("cronJobs.form.scriptPathPlaceholder")}
      allowClear
      showSearch
      treeLine
      loading={loading}
      notFoundContent={
        loading ? <Spin size="small" /> : t("cronJobs.form.scriptPathEmpty")
      }
      onChange={(next) => onChange?.(typeof next === "string" ? next : "")}
      loadData={async (node) => {
        const raw = String(node.value ?? "");
        if (!raw.startsWith("dir:")) return;
        await fetchDir(raw.slice("dir:".length));
      }}
      onOpenChange={(open) => {
        if (!open || !agentId) return;
        setLoading(true);
        void fetchDir("").finally(() => setLoading(false));
      }}
    />
  );
}
