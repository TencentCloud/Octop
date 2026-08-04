import { beforeEach, describe, expect, it } from "vitest";
import { terminalStoreTestApi } from "./useTerminal.testUtils";

describe("ensureDefaultSession", () => {
  beforeEach(() => {
    terminalStoreTestApi.reset();
    localStorage.removeItem("octop:terminal-sessions");
  });

  it("creates one session when the store is empty", () => {
    terminalStoreTestApi.ensureDefaultSession();
    expect(terminalStoreTestApi.getSessionIds()).toHaveLength(1);
  });

  it("does not create another session when one already exists", () => {
    terminalStoreTestApi.createSession();
    const before = terminalStoreTestApi.getSessionIds();
    terminalStoreTestApi.ensureDefaultSession();
    terminalStoreTestApi.ensureDefaultSession();
    expect(terminalStoreTestApi.getSessionIds()).toEqual(before);
  });

  it("does not add a session after remount-style repeated seeds", () => {
    terminalStoreTestApi.ensureDefaultSession();
    const first = terminalStoreTestApi.getSessionIds();
    // Simulate chat dock close/open: seed runs again on a fresh TerminalPage.
    terminalStoreTestApi.ensureDefaultSession();
    terminalStoreTestApi.ensureDefaultSession();
    expect(terminalStoreTestApi.getSessionIds()).toEqual(first);
  });
});
