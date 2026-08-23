import type { ComponentType } from "react";

/** Parsed ``octop_ui`` envelope from a tool JSON string output. */
export interface OctopUiHint {
  renderer: string;
  version?: number;
}

export interface ParsedToolOutput {
  /** True when ``output`` parsed as JSON object. */
  isJson: boolean;
  raw: unknown;
  octopUi?: OctopUiHint;
  data?: unknown;
  text?: string;
}

export type ToolRenderStatus = "running" | "done" | "error";

export interface ToolRenderContext {
  agentId: string | null;
  threadId: string | null;
  locale: string;
  theme: "light" | "dark";
}

export interface ToolRenderProps {
  pluginId: string;
  toolName: string;
  displayName?: string;
  callId?: string;
  status: ToolRenderStatus;
  args: unknown;
  /** Parsed ``data`` field, or full parsed object / raw string. */
  data: unknown;
  textFallback?: string;
  host: OctopPluginUIHost;
  /** Original tool output string (for builtins that need media parsing). */
  output?: string;
  isStreaming: boolean;
  hideMediaPreview?: boolean;
  onAcpPermissionSelect?: (message: string) => void;
  agentId?: string | null;
}

export interface ToolRendererRegistration {
  /** Plugin-local renderer id (matches ``octop_ui.renderer``). */
  id: string;
  /** Owning plugin id (``builtin`` for first-party renderers). */
  pluginId: string;
  /** Tool names this renderer handles when ``octop_ui`` is absent. */
  tools?: string[];
  component: ComponentType<ToolRenderProps>;
}

export interface OctopPluginUIHost {
  registerRenderer(
    reg: Omit<ToolRendererRegistration, "pluginId"> & { pluginId?: string },
  ): void;
  getToolContext(): ToolRenderContext;
  /** L2: update display payload for a tool call without re-running the LLM. */
  patchResult(callId: string, nextData: unknown): void;
  /** Authenticated Octop API request (path starts with ``/`` under ``/api``). */
  request<T = unknown>(path: string, init?: RequestInit): Promise<T>;
}

/** Shape expected from ``ui/dist/index.js``. */
export interface PluginUiModule {
  setup?: (host: OctopPluginUIHost) => void;
  default?: { setup?: (host: OctopPluginUIHost) => void };
}

export interface PluginUiManifest {
  renderers?: Array<{
    id: string;
    tools?: string[];
  }>;
}
