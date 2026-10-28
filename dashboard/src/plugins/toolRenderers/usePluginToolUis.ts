import { useEffect } from "react";
import { pluginsApi } from "../../api/modules/plugins";
import {
  ensureBuiltinToolRenderers,
  loadInstalledPluginUis,
  resetPluginUiLoader,
  setPluginUiToolContext,
} from "../toolRenderers";
import { updateToolPluginIndex } from "../toolRenderers/toolPluginIndex";

/**
 * Load builtin + installed plugin UI modules once per app session, and keep
 * the tool→plugin index fresh for chat renderer resolution.
 */
export function usePluginToolUis(
  opts: {
    agentId?: string | null;
    threadId?: string | null;
    enabled?: boolean;
  } = {},
): void {
  const { agentId, threadId, enabled = true } = opts;

  useEffect(() => {
    ensureBuiltinToolRenderers();
  }, []);

  useEffect(() => {
    if (agentId === undefined && threadId === undefined) return;
    setPluginUiToolContext({
      agentId: agentId ?? null,
      threadId: threadId ?? null,
    });
  }, [agentId, threadId]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      try {
        const plugins = await pluginsApi.list();
        if (cancelled) return;
        updateToolPluginIndex(plugins);
        await loadInstalledPluginUis(plugins);
      } catch (err) {
        console.warn("[plugin-ui] list/load failed:", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled]);
}

/**
 * Layout-level plugin lifetime: load once per signed-in layout mount and clean
 * up exactly once on unmount. Sign-out is an SPA navigation, so this unmount is
 * the only teardown hook; cleanup must not depend on a page reload.
 */
export function usePluginUiLifecycle(): void {
  usePluginToolUis();
  useEffect(() => resetPluginUiLoader, []);
}
