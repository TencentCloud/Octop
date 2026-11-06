import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getSnapshot,
  reconcileTurnActive,
  removeSession,
  sendTurn,
} from "./chatStore";

const SESSION = "test-reconcile-turn-active";

describe("reconcileTurnActive", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    removeSession(SESSION);
  });

  it("seals a sticky stream once the server reports no active turn", async () => {
    // A turn whose terminal frame never arrives: isStreaming stays true and the
    // footer keeps saying 生成中 while the server has nothing running.
    const turn = sendTurn(SESSION, "hi", "agent-1", "", undefined);
    expect(getSnapshot(SESSION).isStreaming).toBe(true);

    // Past the grace window that protects a just-sent turn (send → subscribe).
    const realNow = Date.now();
    vi.spyOn(Date, "now").mockReturnValue(realNow + 60_000);

    reconcileTurnActive(SESSION, false);

    expect(getSnapshot(SESSION).isStreaming).toBe(false);
    await turn.catch(() => undefined);
  });

  it("keeps a freshly sent turn while it is still inside the grace window", async () => {
    const turn = sendTurn(SESSION, "hi", "agent-1", "", undefined);

    // No clock jump: the server may simply not have registered the turn yet.
    reconcileTurnActive(SESSION, false);

    expect(getSnapshot(SESSION).isStreaming).toBe(true);
    await turn.catch(() => undefined);
  });

  it("keeps the stream while the server still reports an active turn", async () => {
    const turn = sendTurn(SESSION, "hi", "agent-1", "", undefined);

    const realNow = Date.now();
    vi.spyOn(Date, "now").mockReturnValue(realNow + 60_000);
    reconcileTurnActive(SESSION, true);

    expect(getSnapshot(SESSION).isStreaming).toBe(true);
    await turn.catch(() => undefined);
  });

  it("is a no-op for an idle session", () => {
    expect(() => reconcileTurnActive("never-used-session", false)).not.toThrow();
    expect(getSnapshot("never-used-session").isStreaming).toBe(false);
    removeSession("never-used-session");
  });
});
