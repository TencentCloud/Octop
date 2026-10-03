import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const initialize = vi.fn();

vi.mock("mermaid", () => ({
  default: {
    initialize,
  },
}));

describe("mermaidLoader security configuration", () => {
  beforeEach(() => {
    vi.resetModules();
    initialize.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("initializes with securityLevel 'strict', never 'loose'", async () => {
    const { loadMermaid } = await import("./mermaidLoader");
    await loadMermaid();
    expect(initialize).toHaveBeenCalledTimes(1);
    const config = initialize.mock.calls[0][0] as Record<string, unknown>;
    expect(config.securityLevel).toBe("strict");
    expect(config.securityLevel).not.toBe("loose");
  });

  it("initializes exactly once across repeated loads", async () => {
    const { loadMermaid } = await import("./mermaidLoader");
    await loadMermaid();
    await loadMermaid();
    await loadMermaid();
    expect(initialize).toHaveBeenCalledTimes(1);
  });
});
