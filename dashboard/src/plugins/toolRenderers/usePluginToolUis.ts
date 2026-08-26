import { useEffect, useRef } from "react";
import { pluginsApi } from "../../api/modules/plugins";
import {
  ensureBuiltinToolRenderers,
  loadInstalledPluginUis,
  setPluginUiToolContext,
} from "../toolRenderers";
import { updateToolPluginIndex } from "../toolRenderers/toolPluginIndex";

/**
 * Load builtin + installed plugin UI modules once per app session, and keep
 * the tool→plugin index fresh for chat renderer resolution.
 */
export function usePluginToolUis(opts: {
  agentId?: string | null;
  threadId?: string | null;
  enabled?: boolean;
}): void {
  const { agentId = null, threadId = null, enabled = true } = opts;
  const loading = useRef(false);

  useEffect(() => {
    ensureBuiltinToolRenderers();
  }, []);

  useEffect(() => {
    setPluginUiToolContext({ agentId, threadId });
  }, [agentId, threadId]);

  useEffect(() => {
    if (!enabled || loading.current) return;
    let cancelled = false;
    loading.current = true;
    (async () => {
      try {
        const plugins = await pluginsApi.list();
        if (cancelled) return;
        updateToolPluginIndex(plugins);
        await loadInstalledPluginUis(plugins);
      } catch (err) {
        console.warn("[plugin-ui] list/load failed:", err);
      } finally {
        loading.current = false;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled]);
}
