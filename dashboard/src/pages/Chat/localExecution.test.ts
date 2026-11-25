import { afterEach, describe, expect, it } from "vitest";
import { EMPTY_CHAT_SESSION_KEY, PENDING_THREAD_ID } from "./constants";
import {
  isDraftExecutionThread,
  localDirectoryForTurn,
  localDirectoryMissing,
  pathTail,
  pinLocalExecution,
  readLocalExecution,
  writeLocalExecution,
  type LocalExecutionChoice,
} from "./localExecution";

const AGENT = "bridge:conn:EXPERT1";
const OTHER_AGENT = "bridge:conn:EXPERT2";
const LOCAL_AGENT = "local-agent";

const LOCAL: LocalExecutionChoice = {
  mode: "local",
  directory: "/home/me/notes",
  workspaces: [],
};

function agentKey(agent: string): string {
  return `octop.bridge.exec.agent.${agent}`;
}

function threadKey(agent: string, thread: string): string {
  return `octop.bridge.exec.thread.${agent}.${thread}`;
}

function setKey(key: string, value: LocalExecutionChoice): void {
  localStorage.setItem(key, JSON.stringify(value));
}

function clearAll(): void {
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith("octop.bridge.exec.")) localStorage.removeItem(key);
  }
}

describe("localExecution", () => {
  afterEach(clearAll);

  describe("readLocalExecution", () => {
    it("is always cloud for a non-bridge agent", () => {
      setKey(agentKey(LOCAL_AGENT), LOCAL);
      expect(readLocalExecution(LOCAL_AGENT, null)).toEqual({
        mode: "cloud",
        directory: "",
        workspaces: [],
      });
    });

    it("reads the agent draft key for a draft thread", () => {
      setKey(agentKey(AGENT), LOCAL);
      expect(readLocalExecution(AGENT, null)).toEqual(LOCAL);
      expect(readLocalExecution(AGENT, EMPTY_CHAT_SESSION_KEY)).toEqual(LOCAL);
      expect(readLocalExecution(AGENT, PENDING_THREAD_ID)).toEqual(LOCAL);
    });

    it("reads the thread key for a real thread and does not inherit the agent default", () => {
      setKey(agentKey(AGENT), LOCAL);
      expect(readLocalExecution(AGENT, "thr_123")).toEqual({
        mode: "cloud",
        directory: "",
        workspaces: [],
      });
      setKey(threadKey(AGENT, "thr_123"), LOCAL);
      expect(readLocalExecution(AGENT, "thr_123")).toEqual(LOCAL);
    });

    it("ignores corrupt storage", () => {
      localStorage.setItem(agentKey(AGENT), "{not-json");
      expect(readLocalExecution(AGENT, null)).toEqual({
        mode: "cloud",
        directory: "",
        workspaces: [],
      });
    });

    it("normalizes a malformed stored choice", () => {
      localStorage.setItem(
        agentKey(AGENT),
        JSON.stringify({ mode: "weird", directory: 42, workspaces: [1, "ok"] }),
      );
      const choice = readLocalExecution(AGENT, null);
      expect(choice.mode).toBe("cloud");
      expect(choice.directory).toBe("");
      expect(choice.workspaces).toEqual(["ok"]);
    });
  });

  describe("writeLocalExecution", () => {
    it("writes the agent key for a draft thread", () => {
      writeLocalExecution(AGENT, null, LOCAL);
      expect(readLocalExecution(AGENT, null)).toEqual(LOCAL);
    });

    it("refuses to overwrite a real thread's pinned choice", () => {
      writeLocalExecution(AGENT, "thr_123", LOCAL);
      expect(localStorage.getItem(threadKey(AGENT, "thr_123"))).toBeNull();
    });

    it("is a no-op for a non-bridge agent", () => {
      writeLocalExecution(LOCAL_AGENT, null, LOCAL);
      expect(localStorage.getItem(agentKey(LOCAL_AGENT))).toBeNull();
    });
  });

  describe("pinLocalExecution", () => {
    it("copies the agent draft choice onto a new thread once", () => {
      setKey(agentKey(AGENT), LOCAL);
      pinLocalExecution(AGENT, "thr_123");
      expect(readLocalExecution(AGENT, "thr_123")).toEqual(LOCAL);
    });

    it("does not overwrite an already-pinned thread", () => {
      setKey(agentKey(AGENT), LOCAL);
      const pinned: LocalExecutionChoice = {
        mode: "local",
        directory: "/data/other",
        workspaces: [],
      };
      setKey(threadKey(AGENT, "thr_123"), pinned);
      pinLocalExecution(AGENT, "thr_123");
      expect(readLocalExecution(AGENT, "thr_123")).toEqual(pinned);
    });

    it("is a no-op for a draft thread id", () => {
      setKey(agentKey(AGENT), LOCAL);
      pinLocalExecution(AGENT, PENDING_THREAD_ID);
      expect(
        localStorage.getItem(threadKey(AGENT, PENDING_THREAD_ID)),
      ).toBeNull();
    });
  });

  describe("localDirectoryMissing", () => {
    it("is true when local has no directory", () => {
      writeLocalExecution(AGENT, null, {
        mode: "local",
        directory: "",
        workspaces: [],
      });
      expect(localDirectoryMissing(AGENT, null)).toBe(true);
    });

    it("is false when cloud", () => {
      expect(localDirectoryMissing(AGENT, null)).toBe(false);
    });

    it("is false when local has a directory", () => {
      writeLocalExecution(AGENT, null, LOCAL);
      expect(localDirectoryMissing(AGENT, null)).toBe(false);
    });
  });

  describe("pathTail", () => {
    it("keeps the last two segments", () => {
      expect(pathTail("/home/me/.octop/agents/EXPERT1")).toBe("agents/EXPERT1");
      expect(pathTail("")).toBe("");
    });

    it("treats a real thread as locked", () => {
      expect(isDraftExecutionThread(null)).toBe(true);
      expect(isDraftExecutionThread("thr_1")).toBe(false);
    });
  });

  describe("localDirectoryForTurn", () => {
    it("returns null for a draft thread", () => {
      setKey(agentKey(AGENT), LOCAL);
      expect(localDirectoryForTurn(AGENT, null)).toBeNull();
    });

    it("returns null for a non-bridge agent", () => {
      expect(localDirectoryForTurn(LOCAL_AGENT, "thr_1")).toBeNull();
    });

    it("returns the directory for a pinned local thread", () => {
      setKey(threadKey(AGENT, "thr_1"), LOCAL);
      expect(localDirectoryForTurn(AGENT, "thr_1")).toBe("/home/me/notes");
    });

    it("returns null for a pinned cloud thread", () => {
      setKey(threadKey(AGENT, "thr_1"), {
        mode: "cloud",
        directory: "",
        workspaces: [],
      });
      expect(localDirectoryForTurn(AGENT, "thr_1")).toBeNull();
    });

    it("returns null when the stored directory is blank", () => {
      setKey(threadKey(AGENT, "thr_1"), {
        mode: "local",
        directory: "  ",
        workspaces: [],
      });
      expect(localDirectoryForTurn(AGENT, "thr_1")).toBeNull();
    });

    it("keeps each agent's storage separate", () => {
      setKey(threadKey(AGENT, "thr_1"), LOCAL);
      setKey(threadKey(OTHER_AGENT, "thr_1"), {
        mode: "local",
        directory: "/other",
        workspaces: [],
      });
      expect(localDirectoryForTurn(AGENT, "thr_1")).toBe("/home/me/notes");
      expect(localDirectoryForTurn(OTHER_AGENT, "thr_1")).toBe("/other");
    });
  });

  describe("workspaces", () => {
    it("round-trips the extra workspaces list", () => {
      const choice: LocalExecutionChoice = {
        mode: "local",
        directory: "/home/me/notes",
        workspaces: ["/home/me/notes", "/data/proj", "/tmp/x"],
      };
      writeLocalExecution(AGENT, null, choice);
      expect(readLocalExecution(AGENT, null).workspaces).toEqual([
        "/home/me/notes",
        "/data/proj",
        "/tmp/x",
      ]);
    });

    it("drops non-string and blank entries on load", () => {
      localStorage.setItem(
        agentKey(AGENT),
        JSON.stringify({
          mode: "local",
          directory: "/x",
          workspaces: ["ok", "", 3, "good"],
        }),
      );
      expect(readLocalExecution(AGENT, null).workspaces).toEqual([
        "ok",
        "good",
      ]);
    });
  });
});
