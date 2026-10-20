import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { applySlot, buildPluginConfig, chooseCandidates, parseProbeReport } from "./setup.ts";

describe("parseProbeReport", () => {
  it("parses the last JSON line", () => {
    const out = 'noise\n{"ok":true,"fts5":true,"sqlite_version":"3.45.1","protocol_version":"1.0"}\n';
    const report = parseProbeReport(out);
    assert.equal(report?.ok, true);
    assert.equal(report?.fts5, true);
    assert.equal(report?.sqlite_version, "3.45.1");
  });

  it("returns null on non-JSON / missing ok", () => {
    assert.equal(parseProbeReport("Traceback ...\nno such module: fts5"), null);
    assert.equal(parseProbeReport('{"sqlite_version":"3.45.1"}'), null);
    assert.equal(parseProbeReport(""), null);
  });
});

describe("chooseCandidates", () => {
  it("prefers --bridge-command, then PATH script, then python -m", () => {
    const c = chooseCandidates({ bridgeCommand: "/x/octopmemory-bridge" });
    assert.equal(c[0].source, "--bridge-command");
    assert.equal(c[0].command, "/x/octopmemory-bridge");
    assert.deepEqual(c[0].prefixArgs, []);
    // python -m fallback is always last.
    const last = c[c.length - 1];
    assert.equal(last.command, "python3");
    assert.deepEqual(last.prefixArgs, ["-m", "octop_memory.adapters.bridge.server"]);
  });

  it("includes existing config command and de-dupes", () => {
    const c = chooseCandidates({}, "octopmemory-bridge");
    const keys = c.map((x) => `${x.command} ${x.prefixArgs.join(" ")}`);
    assert.equal(new Set(keys).size, keys.length, "no duplicates");
  });
});

describe("buildPluginConfig", () => {
  it("produces an FTS-only balanced block with bridge.command", () => {
    const cfg = buildPluginConfig({ profile: "balanced", namespace: "ns1" }, "/tools/bin/octopmemory-bridge") as Record<
      string,
      Record<string, unknown>
    >;
    assert.equal((cfg as Record<string, unknown>).profile, "balanced");
    assert.equal((cfg as Record<string, unknown>).mode, "self-hosted");
    assert.equal((cfg as Record<string, unknown>).namespace, "ns1");
    assert.equal(cfg.bridge.command, "/tools/bin/octopmemory-bridge");
    assert.equal(cfg.capture.agent_end_hook, true); // autoCapture on by default
    assert.equal(cfg.recall.mode, "tool_hint");
    // sqlite is the default backend and is omitted from the written config.
    assert.equal((cfg as Record<string, unknown>).backend, undefined);
  });

  it("writes backend=postgres explicitly, never a DSN", () => {
    const cfg = buildPluginConfig(
      { profile: "balanced", namespace: "ns1", backend: "postgres" },
      "/tools/bin/octopmemory-bridge",
    ) as Record<string, unknown>;
    assert.equal(cfg.backend, "postgres");
    assert.ok(!Object.keys(cfg).some((k) => k.toLowerCase().includes("dsn")));
  });
});

describe("applySlot", () => {
  it("sets the slot + entry on an empty config without takeover", () => {
    const { config, takeover } = applySlot({}, { profile: "balanced" });
    const plugins = config.plugins as Record<string, Record<string, unknown>>;
    assert.equal(plugins.slots.memory, "octopmemory");
    assert.deepEqual(plugins.entries.octopmemory, {
      enabled: true,
      hooks: { allowConversationAccess: true },
      config: { profile: "balanced" },
    });
    assert.equal(takeover, undefined);
  });

  it("preserves unrelated keys and reports takeover from another memory plugin", () => {
    const existing = {
      someTopLevel: 1,
      plugins: { slots: { memory: "memory-core" }, entries: { other: { enabled: true } } },
    };
    const { config, takeover } = applySlot(existing, { profile: "privacy" });
    assert.equal(config.someTopLevel, 1);
    const plugins = config.plugins as Record<string, Record<string, unknown>>;
    assert.equal(plugins.slots.memory, "octopmemory");
    assert.ok(plugins.entries.other, "preserves other entries");
    assert.equal(takeover, "memory-core");
  });

  it("does not report takeover when slot was already us", () => {
    const { takeover } = applySlot({ plugins: { slots: { memory: "octopmemory" } } }, {});
    assert.equal(takeover, undefined);
  });
});
