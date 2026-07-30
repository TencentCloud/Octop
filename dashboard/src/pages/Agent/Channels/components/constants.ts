import qqIcon from "../../../../assets/channels/qq.svg";
import discordIcon from "../../../../assets/channels/discord.svg";
import dingtalkIcon from "../../../../assets/channels/dingtalk.svg";
import feishuIcon from "../../../../assets/channels/feishu.svg";
import dashboardIcon from "../../../../assets/channels/dashboard.svg";
import yuanbaoIcon from "../../../../assets/channels/yuanbao.svg";
import wecomIcon from "../../../../assets/channels/wecom.svg";
import weixinIcon from "../../../../assets/channels/weixin.svg";
import octopIcon from "../../../../assets/channels/octop.svg";
import consoleIcon from "../../../../assets/channels/console.svg";
import telegramIcon from "../../../../assets/channels/telegram.svg";
import mqttIcon from "../../../../assets/channels/mqtt.png";
import xiaoyiIcon from "../../../../assets/channels/xiaoyi.png";

/**
 * Catalogue of channel kinds the octop backend's ``ChannelFactory`` knows
 * how to build. Source of truth: ``octop/channels/factory.py``.
 */
export type ChannelKey =
  | "feishu"
  | "dingtalk"
  | "wecom"
  | "qq"
  | "weixin"
  | "discord"
  | "yuanbao"
  | "xiaoyi"
  | "mqtt"
  | "telegram"
  | "dashboard"
  | "agentchat"
  | "octopbot";

/**
 * Channel kinds backed by Octop ``ChannelKind`` / harness-gateway ``BUILTIN_CHANNELS``.
 * ``dashboard`` / ``agentchat`` / ``discord`` are intentionally omitted until implemented.
 */
export const CHANNEL_KEYS: ChannelKey[] = [
  "weixin",
  "qq",
  "wecom",
  "feishu",
  "yuanbao",
  "dingtalk",
  "telegram",
  "xiaoyi",
  "mqtt",
];

/** i18n key for each channel's display name (``channels.label_{key}``). */
export const CHANNEL_LABEL_KEYS: Record<ChannelKey, string> = {
  feishu: "channels.label_feishu",
  dingtalk: "channels.label_dingtalk",
  wecom: "channels.label_wecom",
  qq: "channels.label_qq",
  weixin: "channels.label_weixin",
  discord: "channels.label_discord",
  yuanbao: "channels.label_yuanbao",
  xiaoyi: "channels.label_xiaoyi",
  mqtt: "channels.label_mqtt",
  telegram: "channels.label_telegram",
  dashboard: "channels.label_dashboard",
  agentchat: "channels.label_agentchat",
  octopbot: "channels.label_octopbot",
};

/** Hardcoded Chinese labels used as fallback when t() returns the key. */
export const CHANNEL_LABELS: Record<ChannelKey, string> = {
  weixin: "微信",
  qq: "QQ",
  wecom: "企业微信",
  feishu: "飞书",
  yuanbao: "元宝",
  dingtalk: "钉钉",
  discord: "Discord",
  xiaoyi: "小艺",
  mqtt: "MQTT",
  telegram: "Telegram",
  dashboard: "控制台",
  agentchat: "AgentChat",
  octopbot: "OctopBot",
};

export const CHANNEL_ICONS: Record<ChannelKey, string> = {
  feishu: feishuIcon,
  dingtalk: dingtalkIcon,
  wecom: wecomIcon,
  qq: qqIcon,
  weixin: weixinIcon,
  discord: discordIcon,
  yuanbao: yuanbaoIcon,
  xiaoyi: xiaoyiIcon,
  mqtt: mqttIcon,
  telegram: telegramIcon,
  dashboard: dashboardIcon,
  agentchat: consoleIcon,
  octopbot: octopIcon,
};

/** Brand accent per channel — used for cron task card stripes, badges, etc. */
export const CHANNEL_COLORS: Record<ChannelKey, string> = {
  weixin: "#07C160",
  qq: "#12B7F5",
  wecom: "#0188FB",
  feishu: "#3370FF",
  yuanbao: "#E8A317",
  dingtalk: "#0089FF",
  telegram: "#229ED9",
  xiaoyi: "#CF0A2C",
  mqtt: "#7C3AED",
  discord: "#5865F2",
  dashboard: "#6366F1",
  agentchat: "#64748B",
  octopbot: "#10B981",
};

export function getChannelColor(channel: string): string {
  if (Object.prototype.hasOwnProperty.call(CHANNEL_COLORS, channel)) {
    return CHANNEL_COLORS[channel as ChannelKey];
  }
  return "#8c8c8c";
}

/** External onboarding/credential URLs. */
export const CHANNEL_URLS: Partial<Record<ChannelKey, string>> = {
  feishu: "https://open.feishu.cn/app",
  dingtalk: "https://open-dev.dingtalk.com/",
  qq: "https://q.qq.com/qqbot/openclaw/",
  discord: "https://discord.com/developers/applications",
  yuanbao: "https://yuanbao.tencent.com/bot",
  wecom: "https://work.weixin.qq.com/wework_admin/frame#/aiHelper/create",
  telegram: "https://t.me/BotFather",
  octopbot: "https://octop.cloud.tencent.com",
};

/** A single field of a channel's config form. */
export interface ChannelField {
  /** ``config`` JSON key. */
  name: string;
  /** Visible label (Chinese; falls back when no i18n key). */
  label: string;
  /** Antd input type. */
  type?: "text" | "password" | "textarea";
  /** Placeholder for the input. */
  placeholder?: string;
  /** True when the field is required at create time. */
  required?: boolean;
}

/**
 * Per-kind config field schema. Drives ``ChannelDrawer``'s manual config
 * form. Kinds not listed here fall back to a JSON textarea so any
 * harness-gateway channel still works without UI changes.
 */
export const CHANNEL_FIELDS: Partial<Record<ChannelKey, ChannelField[]>> = {
  feishu: [
    { name: "app_id", label: "App ID", placeholder: "cli_xxx", required: true },
    {
      name: "app_secret",
      label: "App Secret",
      type: "password",
      required: true,
    },
    { name: "encrypt_key", label: "Encrypt Key", type: "password" },
    {
      name: "verification_token",
      label: "Verification Token",
      type: "password",
    },
  ],
  dingtalk: [
    {
      name: "client_id",
      label: "Client ID",
      placeholder: "dingxxxxxx",
      required: true,
    },
    {
      name: "client_secret",
      label: "Client Secret",
      type: "password",
      required: true,
    },
  ],
  wecom: [
    { name: "bot_id", label: "Bot ID", required: true },
    { name: "secret", label: "Secret", type: "password", required: true },
    {
      name: "websocket_url",
      label: "WebSocket URL",
      placeholder: "wss://openws.work.weixin.qq.com",
    },
  ],
  qq: [
    { name: "app_id", label: "App ID", required: true },
    { name: "secret", label: "App Secret", type: "password", required: true },
  ],
  discord: [
    { name: "bot_token", label: "Bot Token", type: "password", required: true },
    {
      name: "http_proxy",
      label: "HTTP Proxy",
      placeholder: "http://127.0.0.1:18118",
    },
    {
      name: "http_proxy_auth",
      label: "HTTP Proxy Auth",
      placeholder: "user:password",
    },
  ],
  yuanbao: [
    { name: "app_key", label: "App Key", required: true },
    {
      name: "app_secret",
      label: "App Secret",
      type: "password",
      required: true,
    },
    {
      name: "api_domain",
      label: "API Domain",
      placeholder: "bot.yuanbao.tencent.com",
    },
    {
      name: "ws_url",
      label: "WebSocket URL",
      placeholder: "wss://bot-wss.yuanbao.tencent.com/wss/connection",
    },
  ],
  weixin: [
    { name: "bot_uin", label: "机器人 UIN", required: true },
    { name: "token", label: "Token", type: "password", required: true },
    { name: "base_url", label: "Base URL" },
  ],
  octopbot: [
    { name: "api_key", label: "API Key", type: "password", required: true },
    { name: "api_base_url", label: "API Base URL", required: true },
  ],
  xiaoyi: [
    { name: "ak", label: "Access Key (AK)", required: true },
    { name: "sk", label: "Secret Key (SK)", type: "password", required: true },
    { name: "agent_id", label: "Agent ID", required: true },
    { name: "ws_url", label: "WebSocket URL" },
    { name: "ws_url_backup", label: "备用 WebSocket URL" },
  ],
  mqtt: [
    { name: "host", label: "Broker Host", required: true },
    { name: "port", label: "Port", placeholder: "8883" },
    { name: "username", label: "Username" },
    { name: "password", label: "Password", type: "password" },
    {
      name: "subscribe_topic",
      label: "Subscribe Topic",
      placeholder: "devices/+/in",
    },
    {
      name: "publish_topic",
      label: "Publish Topic",
      placeholder: "devices/{client_id}/out",
    },
    { name: "transport", label: "Transport", placeholder: "tcp" },
  ],
  telegram: [
    { name: "bot_token", label: "Bot Token", type: "password", required: true },
    {
      name: "http_proxy",
      label: "HTTP Proxy",
      placeholder: "http://127.0.0.1:18118",
    },
  ],
  // dashboard & agentchat: no required credentials.
};

/** Config keys stored as booleans — excluded from credential string mapping. */
export const CHANNEL_BOOLEAN_CONFIG_KEYS = [
  "show_thinking",
  "show_tool_hints",
] as const;

/** Default per-channel display settings (harness-gateway ChannelConfig). */
export const DEFAULT_CHANNEL_DISPLAY_CONFIG = {
  show_thinking: false,
  show_tool_hints: false,
} as const;

/** Required field names per kind — used for "missing creds" UX. */
export const REQUIRED_CREDENTIALS: Partial<Record<ChannelKey, string[]>> =
  Object.fromEntries(
    Object.entries(CHANNEL_FIELDS).map(([key, fields]) => [
      key,
      (fields ?? []).filter((f) => f.required).map((f) => f.name),
    ]),
  );

/** Whether a config blob has all required credentials for the given kind. */
export function hasRequiredCredentials(
  key: ChannelKey,
  config: Record<string, unknown> | undefined,
): boolean {
  const required = REQUIRED_CREDENTIALS[key];
  if (!required || required.length === 0) return true;
  if (!config) return false;
  return required.every((field) => {
    const v = config[field];
    return v !== undefined && v !== null && String(v).trim() !== "";
  });
}
