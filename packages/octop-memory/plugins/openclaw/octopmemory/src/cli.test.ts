import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { registerOctopmemoryCli, renderSearchResults, renderShowResult, renderStatus } from "./cli.ts";

class FakeCommand {
  readonly children = new Map<string, FakeCommand>();
  handler: ((...args: unknown[]) => unknown) | null = null;
  desc = "";

  command(def: string): FakeCommand {
    const name = def.split(/\s+/)[0] ?? def;
    const child = new FakeCommand();
    this.children.set(name, child);
    return child;
  }

  description(text: string): FakeCommand {
    this.desc = text;
    return this;
  }

  argument(): FakeCommand {
    return this;
  }

  option(): FakeCommand {
    return this;
  }

  allowUnknownOption(): FakeCommand {
    return this;
  }

  action(handler: (...args: unknown[]) => unknown): FakeCommand {
    this.handler = handler;
    return this;
  }
}

describe("octopmemory native CLI", () => {
  it("registers native status/search/show/reindex/dashboard commands", () => {
    const program = new FakeCommand();
    registerOctopmemoryCli(program, fakeApi(), async () => fakeBridge());

    const root = program.children.get("octopmemory");
    assert.ok(root);
    assert.deepEqual([...root.children.keys()].sort(), [
      "admin",
      "dashboard",
      "reindex",
      "search",
      "setup",
      "show",
      "status",
    ]);
  });

  it("stops the bridge after one-shot native commands", async () => {
    const program = new FakeCommand();
    const bridge = fakeBridge();
    registerOctopmemoryCli(program, fakeApi(), async () => bridge);

    const root = program.children.get("octopmemory");
    assert.ok(root);

    const logs: unknown[][] = [];
    const originalLog = console.log;
    console.log = (...args: unknown[]) => {
      logs.push(args);
    };
    try {
      await root.children.get("status")?.handler?.();
      await root.children.get("search")?.handler?.("Mercury", { max: "1", corpus: "all" });
      await root.children.get("show")?.handler?.("atom/atm_1.md", {});
      await root.children.get("reindex")?.handler?.();
    } finally {
      console.log = originalLog;
    }

    assert.equal(bridge.stopCount, 4);
    assert.equal(logs.length, 4);
  });

  it("renders status output", () => {
    const text = renderStatus({
      namespace: "ns",
      counts: { raw_events: 2, atoms: 1, entities: 3, dirty_pages: 0 },
      config: { profile: "balanced", recall_mode: "tool_hint" },
      host_files: { indexed: 2, root: "/workspace", last_scan_iso: "2026-06-04T00:00:00Z" },
    });

    assert.match(text, /Namespace:\s+ns/);
    assert.match(text, /raw=2/);
    assert.match(text, /profile=balanced/);
    assert.match(text, /host_files=2/);
  });

  it("renders search hits", () => {
    const text = renderSearchResults({
      hits: [
        { path: "atom/atm_1.md", layer: "atom", snippet: "Decision: use registerMemoryCapability." },
      ],
    });

    assert.match(text, /atom\/atm_1\.md/);
    assert.match(text, /Decision/);
  });

  it("renders memory_get excerpt", () => {
    const text = renderShowResult({ path: "raw/2026-06-04/evt.md", excerpt: "hello", truncated: false });

    assert.equal(text, "hello");
  });
});

function fakeApi() {
  return {
    id: "octopmemory",
    name: "OctopMemory",
    pluginConfig: {},
  } as never;
}

function fakeBridge() {
  return {
    stopCount: 0,
    call: async (method: string) => {
      if (method === "stats") {
        return { namespace: "ns", counts: { raw_events: 0, atoms: 0, entities: 0, dirty_pages: 0 } };
      }
      if (method === "memory_search") {
        return { hits: [] };
      }
      if (method === "memory_get") {
        return { path: "x", excerpt: "body", truncated: false };
      }
      if (method === "reindex") {
        return { scanned: 0, indexed: 0, removed: 0, skipped_binary: 0 };
      }
      return {};
    },
    stop() {
      this.stopCount += 1;
    },
  };
}
