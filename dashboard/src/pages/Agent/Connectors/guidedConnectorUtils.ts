export type GuidedConnectorKind = "weknora" | "dify";

export function isGuidedConnector(
  kind: string | undefined,
): kind is GuidedConnectorKind {
  return kind === "weknora" || kind === "dify";
}

export function extractHttpUrl(text: string): string | null {
  const match = text.trim().match(/https?:\/\/[^\s<>"']+/i);
  if (!match) return null;
  return match[0].replace(/[),.;，。；）]+$/u, "");
}

export function isDifyMcpServerUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    return (
      ["http:", "https:"].includes(url.protocol) &&
      /^\/mcp\/server\/[^/]+\/mcp\/?$/.test(url.pathname)
    );
  } catch {
    return false;
  }
}

export function consoleUrlFromServiceUrl(
  kind: GuidedConnectorKind,
  value: string,
): string | null {
  try {
    const url = new URL(value.trim());
    if (!["http:", "https:"].includes(url.protocol)) return null;
    if (
      kind === "weknora" &&
      ["127.0.0.1", "localhost"].includes(url.hostname) &&
      url.port === "8080"
    ) {
      return `${url.protocol}//${url.hostname}`;
    }
    return url.origin;
  } catch {
    return null;
  }
}
