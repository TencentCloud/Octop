import type {
  CustomMcpServerSpec,
  CustomMcpServers,
  CustomMcpTransport,
} from "../../../api/modules/connectors";

export type EditorMode = "visual" | "json";

export interface ServerCardState {
  key: string;
  name: string;
  transport: CustomMcpTransport;
  url: string;
  headersText: string;
  command: string;
  argsText: string;
  envText: string;
  enabled: boolean;
  collapsed: boolean;
}

export const EXAMPLE_JSON = `{
  "deepwiki": {
    "url": "https://mcp.deepwiki.com/mcp",
    "transport": "streamable_http"
  }
}`;

/** Stable accent colors for custom MCP cards (avoid all looking the same). */
const MCP_ACCENT_PALETTE = [
  "#0d9488", // teal
  "#2563eb", // blue
  "#7c3aed", // violet
  "#db2777", // pink
  "#ea580c", // orange
  "#0891b2", // cyan
  "#65a30d", // lime
  "#d97706", // amber
  "#4f46e5", // indigo
  "#e11d48", // rose
] as const;

export function accentForServerName(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return MCP_ACCENT_PALETTE[hash % MCP_ACCENT_PALETTE.length];
}

export function headersToText(headers?: Record<string, string>): string {
  if (!headers) return "";
  return Object.entries(headers)
    .map(([k, v]) => `${k}: ${v}`)
    .join("\n");
}

export function parseHeadersText(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const idx = trimmed.indexOf(":");
    if (idx <= 0) {
      throw new Error(`invalid header line: ${trimmed}`);
    }
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1).trim();
    if (!key) throw new Error(`invalid header line: ${trimmed}`);
    out[key] = value;
  }
  return out;
}

export function envToText(env?: Record<string, string>): string {
  if (!env) return "";
  return Object.entries(env)
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");
}

export function parseEnvText(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const idx = trimmed.indexOf("=");
    if (idx <= 0) {
      throw new Error(`invalid env line: ${trimmed}`);
    }
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1);
    if (!key) throw new Error(`invalid env line: ${trimmed}`);
    out[key] = value;
  }
  return out;
}

export function serversToCards(servers: CustomMcpServers): ServerCardState[] {
  return Object.entries(servers).map(([name, spec], index) => ({
    key: `${name}-${index}`,
    name,
    transport: spec.transport === "stdio" ? "stdio" : "streamable_http",
    url: spec.url ?? "",
    headersText: headersToText(spec.headers),
    command: spec.command ?? "",
    argsText: (spec.args ?? []).join("\n"),
    envText: envToText(spec.env),
    enabled: spec.enabled !== false,
    collapsed: true,
  }));
}

export function cardsToServers(cards: ServerCardState[]): CustomMcpServers {
  const servers: CustomMcpServers = {};
  for (const card of cards) {
    const name = card.name.trim();
    if (!name) {
      throw new Error("empty_name");
    }
    if (servers[name]) {
      throw new Error("duplicate_name");
    }
    const spec: CustomMcpServerSpec = {
      transport: card.transport,
      enabled: card.enabled,
    };
    if (card.transport === "streamable_http") {
      spec.url = card.url.trim();
      const headers = parseHeadersText(card.headersText);
      if (Object.keys(headers).length > 0) {
        spec.headers = headers;
      }
    } else {
      spec.command = card.command.trim();
      const args = card.argsText
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      if (args.length > 0) {
        spec.args = args;
      }
      const env = parseEnvText(card.envText);
      if (Object.keys(env).length > 0) {
        spec.env = env;
      }
    }
    servers[name] = spec;
  }
  return servers;
}

export function newCard(
  transport: CustomMcpTransport,
  index: number,
): ServerCardState {
  const base = transport === "stdio" ? "stdio-server" : "http-server";
  return {
    key: `${base}-${Date.now()}-${index}`,
    name: `${base}-${index + 1}`,
    transport,
    url: "",
    headersText: "",
    command: "",
    argsText: "",
    envText: "",
    enabled: true,
    collapsed: false,
  };
}

/** Notify chat composer to refresh connector list after custom MCP save. */
export const CONNECTORS_CHANGED_EVENT = "octop:connectors-changed";

export function notifyConnectorsChanged(): void {
  window.dispatchEvent(new CustomEvent(CONNECTORS_CHANGED_EVENT));
}
