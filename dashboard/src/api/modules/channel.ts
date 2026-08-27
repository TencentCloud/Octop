import { request } from "../request";
import type { ChannelConfig, SingleChannelConfig } from "../types";

/** Channel connection status. */
export interface ChannelStatus {
  status:
    | "connected"
    | "disconnected"
    | "connecting"
    | "not_enabled"
    | "checking";
  reason: string | null;
}

/** Channel credential validation result. */
export interface ChannelCheckResult {
  valid: boolean;
  status:
    | "connected"
    | "disconnected"
    | "connecting"
    | "not_enabled"
    | "checking";
  reason: string | null;
  error_code?: string | null;
}

/** Connection status map for all channels. */
export type ChannelStatusMap = Record<string, ChannelStatus>;

export const channelApi = {
  listChannelTypes: () => request<string[]>("/config/channels/types"),

  listChannels: () => request<ChannelConfig>("/config/channels"),

  updateChannels: (body: ChannelConfig) =>
    request<ChannelConfig>("/config/channels", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  getChannelConfig: (channelName: string) =>
    request<SingleChannelConfig>(
      `/config/channels/${encodeURIComponent(channelName)}`,
    ),

  updateChannelConfig: (channelName: string, body: SingleChannelConfig) =>
    request<SingleChannelConfig>(
      `/config/channels/${encodeURIComponent(channelName)}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
      },
    ),

  /** Get connection status for all channels. */
  getChannelsStatus: () => request<ChannelStatusMap>("/config/channels/status"),

  /** Reconnect the specified channel. */
  reconnectChannel: (channelName: string) =>
    request<{ status: string; channel: string }>(
      `/config/channels/${encodeURIComponent(channelName)}/reconnect`,
      { method: "POST" },
    ),

  /** Validate channel credentials and check connectivity. */
  checkChannel: (channelName: string, credentials?: Record<string, string>) =>
    request<ChannelCheckResult>(
      `/config/channels/${encodeURIComponent(channelName)}/check`,
      {
        method: "POST",
        ...(credentials ? { body: JSON.stringify(credentials) } : {}),
      },
    ),

  getShowToolDetails: () =>
    request<{ show_tool_details: boolean }>("/config/show_tool_details"),

  updateShowToolDetails: (value: boolean) =>
    request<{ show_tool_details: boolean }>("/config/show_tool_details", {
      method: "PUT",
      body: JSON.stringify({ show_tool_details: value }),
    }),

  getShowThinking: () =>
    request<{ show_thinking: boolean }>("/config/show_thinking"),

  updateShowThinking: (value: boolean) =>
    request<{ show_thinking: boolean }>("/config/show_thinking", {
      method: "PUT",
      body: JSON.stringify({ show_thinking: value }),
    }),

  /** Generate a QQ Bot application-binding QR code. */
  qqQrcodeGenerate: (agentId: string) =>
    request<{ qrcode_token: string; qrcode_url: string }>(
      `/agents/${agentId}/channels/qq/qrcode/generate`,
      { method: "POST" },
    ),

  /** Poll QQ Bot QR-code binding result. */
  qqQrcodePoll: (agentId: string, qrcode_token: string) =>
    request<{
      status: string;
      app_id?: string;
      secret?: string;
      user_openid?: string;
      message?: string;
    }>(`/agents/${agentId}/channels/qq/qrcode/poll`, {
      method: "POST",
      body: JSON.stringify({ qrcode_token }),
    }),

  /** Get a WeCom QR code for scan-based registration. */
  wecomQrcodeGenerate: (agentId: string) =>
    request<{ scode: string; auth_url: string }>(
      `/agents/${agentId}/channels/wecom/qrcode/generate`,
      { method: "POST" },
    ),

  /** Poll WeCom QR-code scan result. */
  wecomQrcodePoll: (agentId: string, scode: string) =>
    request<{
      status: string;
      bot_id?: string;
      secret?: string;
      reason?: string;
    }>(`/agents/${agentId}/channels/wecom/qrcode/poll`, {
      method: "POST",
      body: JSON.stringify({ scode }),
    }),

  /** Generate a personal WeChat QR code. */
  weixinQrcodeGenerate: (agentId: string) =>
    request<{ qrcode_token: string; qrcode_url: string }>(
      `/agents/${agentId}/channels/weixin/qrcode/generate`,
      { method: "POST" },
    ),

  /** Poll personal WeChat QR-code scan result. */
  weixinQrcodePoll: (agentId: string, qrcode_token: string) =>
    request<{
      status: string;
      account_id?: string;
      token?: string;
      base_url?: string;
      message?: string;
    }>(`/agents/${agentId}/channels/weixin/qrcode/poll`, {
      method: "POST",
      body: JSON.stringify({ qrcode_token }),
    }),

  /** Start DingTalk one-click application registration. */
  dingtalkQrcodeGenerate: (agentId: string) =>
    request<{
      registration_id: string;
      qrcode_url: string;
      user_code: string;
      expires_in: number;
      interval: number;
    }>(`/agents/${agentId}/channels/dingtalk/qrcode/generate`, {
      method: "POST",
    }),

  /** Poll DingTalk registration; credentials are persisted by the backend. */
  dingtalkQrcodePoll: (agentId: string, registration_id: string) =>
    request<{
      status: "waiting" | "success" | "failed" | "expired";
      channel_id?: string;
      message?: string;
    }>(`/agents/${agentId}/channels/dingtalk/qrcode/poll`, {
      method: "POST",
      body: JSON.stringify({ registration_id }),
    }),

  /** Start the Feishu bot auto-creation flow. */
  feishuBotCreatorStart: (
    agentId: string,
    options?: {
      platform?: "feishu" | "lark";
      avatar_url?: string;
      greeting?: string;
    },
  ) =>
    request<{ status: string; pid: number }>(
      `/agents/${agentId}/channels/feishu/bot-creator/start`,
      {
        method: "POST",
        body: JSON.stringify(options || {}),
      },
    ),

  /** Poll Feishu bot creation progress. */
  feishuBotCreatorPoll: (agentId: string) =>
    request<{
      status: string;
      events: Array<{
        action: string;
        level: string;
        step: string;
        message: string;
        content?: string;
        data?: Record<string, unknown>;
        current?: number;
        total?: number;
      }>;
      qr_token?: string;
      app_id?: string;
      app_secret?: string;
      return_code?: number;
    }>(`/agents/${agentId}/channels/feishu/bot-creator/poll`, {
      method: "POST",
    }),

  /** Stop the Feishu bot creation flow. */
  feishuBotCreatorStop: (agentId: string) =>
    request<{ status: string }>(
      `/agents/${agentId}/channels/feishu/bot-creator/stop`,
      { method: "POST" },
    ),

  /** Start the Yuanbao bot scan-binding flow. */
  yuanbaoBotCreatorStart: (
    agentId: string,
    options?: {
      instance_id?: string;
      ip?: string;
    },
  ) =>
    request<{ status: string; pid: number }>(
      `/agents/${agentId}/channels/yuanbao/bot-creator/start`,
      {
        method: "POST",
        body: JSON.stringify(options || {}),
      },
    ),

  /** Poll Yuanbao bot binding progress. */
  yuanbaoBotCreatorPoll: (agentId: string) =>
    request<{
      status: string;
      events: Array<{
        action: string;
        level: string;
        step: string;
        message: string;
        scan_code?: string;
        scan_url?: string;
        data?: Record<string, unknown>;
        current?: number;
        total?: number;
      }>;
      scan_code?: string;
      scan_url?: string;
      app_key?: string;
      app_secret?: string;
      return_code?: number;
    }>(`/agents/${agentId}/channels/yuanbao/bot-creator/poll`, {
      method: "POST",
    }),

  /** Stop the Yuanbao bot binding flow. */
  yuanbaoBotCreatorStop: (agentId: string) =>
    request<{ status: string }>(
      `/agents/${agentId}/channels/yuanbao/bot-creator/stop`,
      { method: "POST" },
    ),
};
