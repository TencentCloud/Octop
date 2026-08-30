import { describe, expect, it } from "vitest";

import {
  consoleUrlFromServiceUrl,
  extractHttpUrl,
  isDifyMcpServerUrl,
  isGuidedConnector,
} from "./guidedConnectorUtils";

describe("guided connector helpers", () => {
  it("extracts a pasted URL without surrounding prose", () => {
    expect(
      extractHttpUrl(
        "MCP Server URL: https://dify.example.com/mcp/server/code/mcp。",
      ),
    ).toBe("https://dify.example.com/mcp/server/code/mcp");
    expect(extractHttpUrl("sk-secret")).toBeNull();
  });

  it("recognizes only Dify app MCP server routes", () => {
    expect(
      isDifyMcpServerUrl("https://dify.example.com/mcp/server/server-code/mcp"),
    ).toBe(true);
    expect(isDifyMcpServerUrl("https://dify.example.com/v1/chat")).toBe(false);
  });

  it("derives safe console origins", () => {
    expect(
      consoleUrlFromServiceUrl("weknora", "http://127.0.0.1:8080/api/v1"),
    ).toBe("http://127.0.0.1");
    expect(
      consoleUrlFromServiceUrl(
        "dify",
        "https://dify.example.com/mcp/server/code/mcp",
      ),
    ).toBe("https://dify.example.com");
    expect(isGuidedConnector("weknora")).toBe(true);
    expect(isGuidedConnector("notion")).toBe(false);
  });
});
