import { request } from "../request";
import type { ACPConfig, ACPRunnerConfig } from "../types/acp";

function agentPath(agentId: string, suffix = ""): string {
  return `/agents/${encodeURIComponent(agentId)}/acp${suffix}`;
}

function optionalAgentHeaders(
  agentId?: string | null,
): HeadersInit | undefined {
  const id = (agentId ?? "").trim();
  if (!id) return undefined;
  return { "X-Octop-Agent-Id": id };
}

export interface AcpHostStatus {
  runner: string;
  platform: string;
  command: string;
  args: string[];
  binary_found: boolean;
  acp_ok: boolean;
  docs_url?: string;
  install_script: string;
  scripts: Record<string, string>;
  agent_prompt: string;
  can_auto_install: boolean;
  status: "ready" | "missing" | "degraded" | "installed" | "skipped";
  reason: string;
  detail?: string;
}

export interface AcpAskResult {
  ok: boolean;
  prompt: string;
  text: string;
  reason: string;
  detail?: string;
  command: string;
}

export interface AcpHostRequest {
  runner: string;
  command: string;
  args: string[];
  env: Record<string, string>;
}

export const acpApi = {
  /** Global runner definitions (shared by all agents for the current user). */
  getGlobalRunners: (agentId?: string | null) =>
    request<{ runners: Record<string, ACPRunnerConfig> }>("/acp", {
      headers: optionalAgentHeaders(agentId),
    }),

  updateGlobalRunners: (
    runners: Record<string, ACPRunnerConfig>,
    agentId?: string | null,
  ) =>
    request<{ runners: Record<string, ACPRunnerConfig> }>("/acp", {
      method: "PUT",
      body: JSON.stringify({ runners }),
      headers: optionalAgentHeaders(agentId),
    }),

  getRunner: (runnerName: string) =>
    request<ACPRunnerConfig>(`/acp/${encodeURIComponent(runnerName)}`),

  updateRunner: (runnerName: string, body: ACPRunnerConfig) =>
    request<ACPRunnerConfig>(`/acp/${encodeURIComponent(runnerName)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteRunner: (runnerName: string) =>
    request<void>(`/acp/${encodeURIComponent(runnerName)}`, {
      method: "DELETE",
    }),

  probeHost: (body: AcpHostRequest) =>
    request<AcpHostStatus>("/acp/probe", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  askHost: (body: AcpHostRequest) =>
    request<AcpAskResult>("/acp/ask", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  installHost: (body: AcpHostRequest) =>
    request<AcpHostStatus>("/acp/install", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Combined view: global runners + per-agent tool toggle. */
  getConfig: (agentId: string) => request<ACPConfig>(agentPath(agentId)),

  updateConfig: (agentId: string, body: ACPConfig) =>
    request<ACPConfig>(agentPath(agentId), {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  updateToolEnabled: (agentId: string, tool_enabled: boolean) =>
    request<{ tool_enabled: boolean }>(`${agentPath(agentId)}/tool`, {
      method: "PUT",
      body: JSON.stringify({ tool_enabled }),
    }),

  /** @deprecated Prefer acpApi.updateRunner */
  updateAgentRunner: (
    agentId: string,
    runnerName: string,
    body: ACPRunnerConfig,
  ) =>
    request<ACPRunnerConfig>(
      `${agentPath(agentId)}/${encodeURIComponent(runnerName)}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
      },
    ),

  /** @deprecated Prefer acpApi.deleteRunner */
  deleteAgentRunner: (agentId: string, runnerName: string) =>
    request<void>(`${agentPath(agentId)}/${encodeURIComponent(runnerName)}`, {
      method: "DELETE",
    }),
};
