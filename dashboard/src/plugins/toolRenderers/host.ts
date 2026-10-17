import { request } from "../../api/request";
import * as chatStore from "../../pages/Chat/hooks/chatStore";
import i18n from "../../i18n";
import {
  mergePatchedToolOutput,
  parseOctopToolOutput,
} from "./parseToolOutput";
import { registerToolRenderer } from "./registry";
import { registerPluginPage } from "../pages/registry";
import type {
  OctopPluginUIHost,
  PluginPageDeclaration,
  PluginPageHost,
  ToolRenderContext,
  ToolRendererRegistration,
} from "./types";

let contextOverride: Partial<ToolRenderContext> = {};
let dockHandlers: {
  openSidePanel?: (opts: {
    callId: string;
    title?: string;
    toolName?: string;
  }) => void;
  closeSidePanel?: (callId: string) => void;
} = {};

/** Chat page wires dock open/close for plugin ``host.openSidePanel``. */
export function setPluginUiDockHandlers(handlers: typeof dockHandlers): void {
  dockHandlers = handlers;
}

/** Chat page sets agent/thread so plugin UIs can call scoped APIs. */
export function setPluginUiToolContext(
  partial: Partial<ToolRenderContext>,
): void {
  contextOverride = { ...contextOverride, ...partial };
}

function readTheme(): "light" | "dark" {
  if (typeof document === "undefined") return "light";
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark") return "dark";
  if (document.documentElement.classList.contains("dark")) return "dark";
  return "light";
}

function createHost(
  defaultPluginId: string,
  pages: readonly PluginPageDeclaration[] = [],
  pagesEnabled = true,
  isActive = () => true,
): OctopPluginUIHost {
  return {
    registerPage(reg) {
      if (!pagesEnabled || !isActive()) return;
      const declaration = pages.find((page) => page.id === reg.id);
      if (!declaration)
        throw new Error("Plugin page must be declared in its UI manifest");
      registerPluginPage({
        ...declaration,
        pluginId: defaultPluginId,
        component: reg.component,
      });
    },
    registerRenderer(reg) {
      if (!isActive()) return;
      const pluginId = reg.pluginId ?? defaultPluginId;
      const full: ToolRendererRegistration = {
        id: reg.id,
        pluginId,
        tools: reg.tools,
        component: reg.component,
      };
      registerToolRenderer(full);
    },
    getToolContext(): ToolRenderContext {
      return {
        agentId: contextOverride.agentId ?? null,
        threadId: contextOverride.threadId ?? null,
        locale: contextOverride.locale ?? i18n.language ?? "en",
        theme: contextOverride.theme ?? readTheme(),
      };
    },
    patchResult(callId: string, nextData: unknown) {
      if (!callId) return;
      chatStore.patchToolResultData(callId, nextData);
    },
    request<T = unknown>(path: string, init?: RequestInit) {
      return request<T>(path, init);
    },
    openSidePanel(opts) {
      dockHandlers.openSidePanel?.(opts);
    },
    closeSidePanel(callId) {
      dockHandlers.closeSidePanel?.(callId);
    },
  };
}

/** Host bound to ``builtin`` for first-party renderers. */
export const builtinPluginHost: OctopPluginUIHost = createHost("builtin");

/** Build a host scoped to an installed plugin id (for dynamic UI modules). */
export function createPluginUiHost(
  pluginId: string,
  pages: readonly PluginPageDeclaration[] = [],
  pagesEnabled = true,
  isActive = () => true,
): OctopPluginUIHost {
  return createHost(pluginId, pages, pagesEnabled, isActive);
}

/** Only authenticated requests and presentation context are exposed to pages. */
export function createPluginPageHost(): PluginPageHost {
  return {
    request,
    getPageContext: () => ({
      locale: i18n.language ?? "en",
      theme: readTheme(),
    }),
  };
}

export { parseOctopToolOutput, mergePatchedToolOutput };
