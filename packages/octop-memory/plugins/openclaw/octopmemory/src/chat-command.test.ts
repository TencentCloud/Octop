import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { registerChatCommand, runChatCommand } from "./chat-command.ts";
import type { OpenClawPluginApi, RegisterChatCommandOptions } from "./sdk-shim.ts";

function fakeBridge(responses: Record<string, unknown>): {
  calls: Array<{ method: string; params: Record<string, unknown> }>;
  provider: () => Promise<{ call: (method: string, params: Record<string, unknown>) => Promise<unknown> }>;
} {
  const calls: Array<{ method: string; params: Record<string, unknown> }> = [];
  const bridge = {
    call: async (method: string, params: Record<string, unknown>) => {
      calls.push({ method, params });
      if (!(method in responses)) throw new Error(`unexpected bridge method ${method}`);
      return responses[method];
    },
  };
  return { calls, provider: async () => bridge };
}

describe("runChatCommand", () => {
  it("returns usage for empty args and help", async () => {
    const { provider } = fakeBridge({});
    for (const args of ["", "   ", "help"]) {
      const text = await runChatCommand(provider, args);
      assert.match(text, /\/octopmemory status/);
      assert.match(text, /\/octopmemory search/);
    }
  });

  it("status calls stats and renders counts", async () => {
    const { calls, provider } = fakeBridge({
      stats: {
        namespace: "openclaw__test",
        counts: { raw_events: 3, atoms: 1, entities: 0, dirty_pages: 0 },
        config: { profile: "balanced", recall: { mode: "tool_hint" } },
        host_files: null,
      },
    });
    const text = await runChatCommand(provider, "status");
    assert.equal(calls[0]?.method, "stats");
    assert.match(text, /Namespace: openclaw__test/);
    assert.match(text, /raw=3 atoms=1/);
  });

  it("search requires a query and forwards it joined", async () => {
    const { calls, provider } = fakeBridge({
      memory_search: { hits: [{ path: "atom/a1.md", layer: "atom", snippet: "hello  world" }] },
    });
    assert.match(await runChatCommand(provider, "search"), /Usage: \/octopmemory search/);
    const text = await runChatCommand(provider, "search hello world");
    assert.deepEqual(calls[0]?.params, { query: "hello world", maxResults: 5, corpus: "all" });
    assert.match(text, /atom\/a1\.md/);
  });

  it("show forwards path with optional from/lines", async () => {
    const { calls, provider } = fakeBridge({ memory_get: { excerpt: "body", truncated: false } });
    assert.match(await runChatCommand(provider, "show"), /Usage: \/octopmemory show/);
    await runChatCommand(provider, "show atom/a1.md 10 5");
    assert.deepEqual(calls[0]?.params, { path: "atom/a1.md", from: 10, lines: 5 });
    calls.length = 0;
    await runChatCommand(provider, "show atom/a1.md");
    assert.deepEqual(calls[0]?.params, { path: "atom/a1.md" });
  });

  it("reindex renders the scan summary", async () => {
    const { provider } = fakeBridge({ reindex: { scanned: 4, indexed: 2, removed: 0, skipped_binary: 0 } });
    assert.match(await runChatCommand(provider, "reindex"), /scanned=4 indexed=2/);
  });

  it("unknown subcommand falls back to usage", async () => {
    const { provider } = fakeBridge({});
    const text = await runChatCommand(provider, "bogus");
    assert.match(text, /Unknown subcommand "bogus"/);
    assert.match(text, /\/octopmemory status/);
  });
});

describe("registerChatCommand", () => {
  function apiWith(registerCommand?: (opts: RegisterChatCommandOptions) => void): OpenClawPluginApi {
    return {
      id: "octopmemory",
      name: "OctopMemory",
      pluginConfig: {},
      registerMemoryCapability: () => undefined,
      registerTool: () => undefined,
      registerCli: () => undefined,
      registerCommand,
      on: () => undefined,
    } as unknown as OpenClawPluginApi;
  }

  it("is a no-op when the host lacks registerCommand", () => {
    const { provider } = fakeBridge({});
    registerChatCommand(apiWith(undefined), provider);
  });

  it("pre-warms the bridge on registration and swallows warmup failures", async () => {
    let warmups = 0;
    const warmProvider = async () => {
      warmups += 1;
      return fakeBridge({}).provider();
    };
    registerChatCommand(
      apiWith(() => undefined),
      warmProvider,
    );
    await Promise.resolve();
    assert.equal(warmups, 1);

    // A rejecting provider must not produce an unhandled rejection.
    registerChatCommand(
      apiWith(() => undefined),
      async () => {
        throw new Error("bridge down");
      },
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  it("registers name/acceptsArgs and the handler replies with text", async () => {
    let registered: RegisterChatCommandOptions | undefined;
    const { provider } = fakeBridge({
      stats: { namespace: "ns", counts: {}, config: {}, host_files: null },
    });
    registerChatCommand(
      apiWith((opts) => {
        registered = opts;
      }),
      provider,
    );
    assert.equal(registered?.name, "octopmemory");
    assert.equal(registered?.acceptsArgs, true);
    const reply = await registered?.handler({ args: "status" });
    assert.match((reply as { text: string }).text, /Namespace: ns/);
  });

  it("handler converts bridge failures into a text reply", async () => {
    let registered: RegisterChatCommandOptions | undefined;
    const provider = async () => {
      throw new Error("bridge down");
    };
    registerChatCommand(
      apiWith((opts) => {
        registered = opts;
      }),
      provider,
    );
    const reply = await registered?.handler({ args: "status" });
    assert.match((reply as { text: string }).text, /bridge down/);
  });
});
