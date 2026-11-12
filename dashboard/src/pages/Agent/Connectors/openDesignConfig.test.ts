import { describe, expect, it } from "vitest";
import { parseOpenDesignConfigs } from "./openDesignConfig";

describe("OpenDesign launch configuration", () => {
  it("imports daemon install-info and preserves opaque environment", () => {
    expect(
      parseOpenDesignConfigs(
        JSON.stringify({
          command: "node",
          args: ["od.mjs", "mcp"],
          env: { OD_DATA_DIR: "data" },
          daemonUrl: "ignored",
        }),
      )["open-design"],
    ).toEqual({
      command: "node",
      args: ["od.mjs", "mcp"],
      env: { OD_DATA_DIR: "data" },
    });
  });
  it("retains all servers for explicit selection", () => {
    const values = parseOpenDesignConfigs(
      '{"mcpServers":{"a":{"command":"a"},"b":{"command":"b"}}}',
    );
    expect(Object.keys(values)).toEqual(["a", "b"]);
  });
  it("imports OpenCode command arrays", () => {
    expect(
      parseOpenDesignConfigs(
        '{"mcp":{"design":{"command":["node","od.mjs","mcp"],"environment":{"A":"b"}}}}',
      ).design.args,
    ).toEqual(["od.mjs", "mcp"]);
  });
  it.each([
    "{}",
    '{"command":"node","args":"mcp"}',
    '{"command":"node","env":{"SECRET":1}}',
  ])("rejects invalid launch configs", (value) =>
    expect(() => parseOpenDesignConfigs(value)).toThrow(),
  );
});
