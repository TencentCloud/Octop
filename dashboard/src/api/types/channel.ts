export interface BaseChannelConfig {
  enabled: boolean;
  bot_prefix: string;
}

export interface DiscordConfig extends BaseChannelConfig {
  bot_token: string;
  http_proxy: string;
  http_proxy_auth: string;
}

export interface DingTalkConfig extends BaseChannelConfig {
  client_id: string;
  client_secret: string;
}

export interface FeishuConfig extends BaseChannelConfig {
  app_id: string;
  app_secret: string;
  encrypt_key: string;
  verification_token: string;
  media_dir: string;
}

export interface QQConfig extends BaseChannelConfig {
  app_id: string;
  client_secret: string;
  group_context?: {
    enabled?: boolean;
    visibility?: "auto" | "all" | "mention_recent" | "mention_only";
    activation?: "mention" | "always";
    history?: "recent" | "none";
    history_limit?: number;
    history_ttl_seconds?: number;
    clear_after_reply?: boolean;
    groups?: Record<string, Record<string, unknown>>;
  };
}

export type DashboardConfig = BaseChannelConfig;

export interface YuanbaoConfig extends BaseChannelConfig {
  app_key: string;
  app_secret: string;
  token: string;
  identifier: string;
  api_domain: string;
  ws_url: string;
  route_env: string;
}

export interface WeComConfig extends BaseChannelConfig {
  bot_id: string;
  secret: string;
  name: string;
  websocket_url: string;
  dm_policy: "open" | "allowlist" | "pairing" | "disabled";
  allow_from: Array<string | number>;
  group_policy: "open" | "allowlist" | "disabled";
  group_allow_from: Array<string | number>;
  groups: Record<string, { allowFrom?: Array<string | number> }>;
  send_thinking: boolean;
  media_dir: string;
  media_local_roots: string[];
}

export interface WeixinAccountConfig {
  account_id: string;
  account_name: string;
  base_url: string;
  token: string;
  configured: boolean;
  bot_uin: string;
  user_uin: string;
}

export interface WeixinConfig extends BaseChannelConfig {
  media_dir: string;
  show_tool_details: boolean;
  accounts: WeixinAccountConfig[];
}

export interface OctopBotConfig extends BaseChannelConfig {
  api_key: string;
  api_keys: string[];
  api_base_url: string;
  name: string;
  dm_policy: "open" | "allowlist" | "disabled";
  allow_from: string[];
  system_prompt: string;
}

export interface ChannelConfig {
  discord: DiscordConfig;
  dingtalk: DingTalkConfig;
  feishu: FeishuConfig;
  qq: QQConfig;
  yuanbao: YuanbaoConfig;
  dashboard: DashboardConfig;
  wecom: WeComConfig;
  weixin: WeixinConfig;
  octopbot: OctopBotConfig;
}

export type SingleChannelConfig =
  | DiscordConfig
  | DingTalkConfig
  | FeishuConfig
  | QQConfig
  | YuanbaoConfig
  | DashboardConfig
  | WeComConfig
  | WeixinConfig
  | OctopBotConfig;
