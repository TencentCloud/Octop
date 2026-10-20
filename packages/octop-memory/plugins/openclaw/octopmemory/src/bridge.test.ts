import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildBridgeArgs, buildBridgeOnlyArgs, resolveBridgeSpawn } from "./bridge.ts";

describe("buildBridgeArgs", () => {
  it("builds the minimal bridge argv", () => {
    const args = buildBridgeArgs({ namespace: "ns", logLevel: "warning" });

    assert.deepEqual(args, [
      "-m",
      "octop_memory.adapters.bridge.server",
      "--namespace",
      "ns",
      "--log-level",
      "warning",
    ]);
  });

  it("includes db path and host_files options when configured", () => {
    const args = buildBridgeArgs({
      namespace: "ns",
      dbPath: "/tmp/memory.sqlite",
      hostFilesRoot: "/workspace",
      hostFilesAllow: ["topics/*.md", "projects/*.md"],
      hostFilesPollInterval: 5,
    });

    assert.deepEqual(args, [
      "-m",
      "octop_memory.adapters.bridge.server",
      "--namespace",
      "ns",
      "--log-level",
      "info",
      "--db-path",
      "/tmp/memory.sqlite",
      "--host-files-root",
      "/workspace",
      "--host-files-allow",
      "topics/*.md",
      "--host-files-allow",
      "projects/*.md",
      "--host-files-poll-interval",
      "5",
    ]);
  });

  it("passes bridge config as compact JSON", () => {
    const args = buildBridgeArgs({
      namespace: "ns",
      config: { recall: { raw_policy: "never" }, capture: { include_roles: ["user"] } },
    });

    const flagIndex = args.indexOf("--config-json");
    assert.notEqual(flagIndex, -1);
    assert.deepEqual(JSON.parse(args[flagIndex + 1] ?? "{}"), {
      recall: { raw_policy: "never" },
      capture: { include_roles: ["user"] },
    });
  });

  it("omits --backend when unset (sqlite is the server's own default)", () => {
    const args = buildBridgeArgs({ namespace: "ns" });
    assert.ok(!args.includes("--backend"));
  });

  it("omits --backend when explicitly sqlite", () => {
    const args = buildBridgeArgs({ namespace: "ns", backend: "sqlite" });
    assert.ok(!args.includes("--backend"));
  });

  it("passes --backend postgres, never the DSN itself", () => {
    const args = buildBridgeArgs({ namespace: "ns", backend: "postgres" });
    const flagIndex = args.indexOf("--backend");
    assert.notEqual(flagIndex, -1);
    assert.equal(args[flagIndex + 1], "postgres");
    // The DSN has no field on BridgeOptions at all — it must never appear in argv.
    assert.ok(!args.some((a) => a.startsWith("postgresql://")));
  });
});

describe("resolveBridgeSpawn", () => {
  it("launches python -m MODULE when no command is set", () => {
    const { command, args } = resolveBridgeSpawn({ namespace: "ns", python: "/venv/bin/python" });
    assert.equal(command, "/venv/bin/python");
    assert.deepEqual(args.slice(0, 2), ["-m", "octop_memory.adapters.bridge.server"]);
    assert.ok(args.includes("--namespace"));
  });

  it("defaults the interpreter to python3", () => {
    const { command } = resolveBridgeSpawn({ namespace: "ns" });
    assert.equal(command, "python3");
  });

  it("spawns the console script directly and drops the -m prefix when command is set", () => {
    const { command, args } = resolveBridgeSpawn({
      namespace: "ns",
      command: "/tools/bin/octopmemory-bridge",
      python: "/venv/bin/python",
    });
    assert.equal(command, "/tools/bin/octopmemory-bridge");
    assert.ok(!args.includes("-m"));
    assert.deepEqual(args, buildBridgeOnlyArgs({ namespace: "ns" }));
    assert.deepEqual(args.slice(0, 2), ["--namespace", "ns"]);
  });
});
