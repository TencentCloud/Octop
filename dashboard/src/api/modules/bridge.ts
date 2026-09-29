import { request } from "../request";
import type { ResolvedModel } from "../types";
import type { KnowledgeBase, KnowledgeCapability } from "./knowledgeBases";

export interface BridgeConnection {
  connection_id: string;
  peer_base_url: string;
  peer_username: string;
  display_name: string;
  notes: string | null;
  icon_name?: string | null;
  status: string;
  last_error: string | null;
  last_seen_at: number | null;
  auto_reconnect: boolean;
  created_at: number;
  updated_at: number;
  has_password: boolean;
  /** Peer-dialed reverse row: no stored password, this side cannot redial. */
  inbound?: boolean;
}

export interface BridgeRemoteAgent {
  id: string;
  agent_id?: string;
  name?: string;
  description?: string | null;
  icon_url?: string | null;
  icon_name?: string | null;
  color?: string | null;
  state?: string | null;
  kind?: string | null;
  status?: string;
  bridge?: boolean;
  bridge_connection_id?: string;
  remote_agent_id?: string;
  [key: string]: unknown;
}

export interface BridgeProbeAgent {
  agent_id: string;
  name: string;
  description: string | null;
  icon_url: string | null;
  icon_name?: string | null;
  color?: string | null;
  state?: string | null;
  kind?: string | null;
}

export interface BridgeProbeResult {
  peer_base_url: string;
  peer_username: string;
  peer_display_name: string;
  agent_count: number;
  agents: BridgeProbeAgent[];
}

export const bridgeApi = {
  list: () => request<BridgeConnection[]>("/bridge/connections"),

  probe: (body: {
    peer_base_url: string;
    peer_username: string;
    password: string;
  }) =>
    request<BridgeProbeResult>("/bridge/probe", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  probeConnection: (
    connectionId: string,
    body: {
      peer_base_url: string;
      peer_username: string;
      password?: string;
    },
  ) =>
    request<BridgeProbeResult>(
      `/bridge/connections/${encodeURIComponent(connectionId)}/probe`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  create: (body: {
    peer_base_url: string;
    peer_username: string;
    password: string;
    display_name: string;
    notes?: string;
    icon_name?: string;
    connect?: boolean;
  }) =>
    request<BridgeConnection>("/bridge/connections", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  get: (connectionId: string) =>
    request<BridgeConnection>(`/bridge/connections/${connectionId}`),

  connect: (connectionId: string) =>
    request<BridgeConnection>(`/bridge/connections/${connectionId}/connect`, {
      method: "POST",
    }),

  disconnect: (connectionId: string) =>
    request<BridgeConnection>(
      `/bridge/connections/${connectionId}/disconnect`,
      { method: "POST" },
    ),

  patch: (
    connectionId: string,
    body: {
      auto_reconnect?: boolean;
      display_name?: string;
      notes?: string;
      icon_name?: string;
      peer_base_url?: string;
      peer_username?: string;
      /** Omit or empty to keep the stored password. */
      password?: string;
    },
  ) =>
    request<BridgeConnection>(`/bridge/connections/${connectionId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  remove: (connectionId: string) =>
    request<void>(`/bridge/connections/${connectionId}`, { method: "DELETE" }),

  listAgents: (connectionId: string) =>
    request<BridgeRemoteAgent[]>(`/bridge/connections/${connectionId}/agents`),

  listResolvedModels: (connectionId: string) =>
    request<ResolvedModel[]>(
      `/bridge/connections/${connectionId}/providers/resolved`,
    ),

  getActiveModel: (connectionId: string) =>
    request<{ provider_name: string; model: string }>(
      `/bridge/connections/${connectionId}/providers/active-model`,
    ),

  listKnowledgeBases: (connectionId: string) =>
    request<KnowledgeBase[]>(
      `/bridge/connections/${connectionId}/knowledge-bases`,
    ),

  getKnowledgeCapability: (connectionId: string) =>
    request<KnowledgeCapability>(
      `/bridge/connections/${connectionId}/knowledge-bases/capability`,
    ),

  getBrowserEnvStatus: (connectionId: string) =>
    request<{
      playwright: boolean;
      browsers_ok: boolean;
      harness_browser: boolean;
      playwright_chromium?: boolean;
      chrome_path?: string | null;
      chrome_source?: string | null;
      error?: string | null;
    }>(`/bridge/connections/${connectionId}/browser/env-status`),

  getBrowserSessions: (connectionId: string) =>
    request<{
      ok: boolean;
      environment: "desktop" | "headless-server";
      sessions: Array<{
        session_id: string;
        profile_name: string;
        conversation_id: string;
        channel_source: string;
        state: string;
        control_owner: "agent" | "user";
        current_url: string;
        created_at: number;
        last_activity_at: number;
      }>;
    }>(`/bridge/connections/${connectionId}/browser/harness-sessions`),

  browserHandoff: (
    connectionId: string,
    sessionId: string,
    target: "agent" | "user",
    reason = "user_button",
  ) =>
    request<{ ok: boolean; session: unknown }>(
      `/bridge/connections/${connectionId}/browser/sessions/${encodeURIComponent(
        sessionId,
      )}/handoff`,
      {
        method: "POST",
        body: JSON.stringify({ target, reason }),
      },
    ),

  /** Dashboard screencast WS relayed to the peer browser harness. */
  browserStreamWsPath: (connectionId: string) =>
    `/bridge/connections/${encodeURIComponent(connectionId)}/browser-stream/ws`,
};
