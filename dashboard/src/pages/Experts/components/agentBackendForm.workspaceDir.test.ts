import { describe, expect, it } from "vitest";
import {
  createWorkspaceSelection,
  joinWorkspaceDir,
  newWorkspaceAgentId,
  userWorkspaceDir,
} from "./agentBackendForm";

describe("userWorkspaceDir", () => {
  it("returns a trimmed path for host-root local backends", () => {
    expect(
      userWorkspaceDir({
        backendChoice: "local_shell",
        rootDir: "/",
        workspaceDir: "  /data/work  ",
      }),
    ).toBe("/data/work");
    expect(
      userWorkspaceDir({
        backendChoice: "filesystem",
        rootDir: "C:/",
        workspaceDir: "D:/projects",
      }),
    ).toBe("D:/projects");
  });

  it("omits the field when the root is scoped or the value is blank", () => {
    expect(
      userWorkspaceDir({
        backendChoice: "local_shell",
        rootDir: "/data/jail",
        workspaceDir: "/data/work",
      }),
    ).toBeUndefined();
    expect(
      userWorkspaceDir({
        backendChoice: "composite",
        rootDir: "/",
        workspaceDir: "/data/work",
      }),
    ).toBeUndefined();
    expect(
      userWorkspaceDir({
        backendChoice: "filesystem",
        rootDir: "/",
        workspaceDir: "   ",
      }),
    ).toBeUndefined();
  });

  it("keeps the prefilled default path tied to its id", () => {
    const id = newWorkspaceAgentId();
    expect(id).toMatch(/^[0-9A-HJKMNP-TV-Z]{6}$/);
    const path = joinWorkspaceDir("/home/u/.octop/agents", id);
    expect(
      createWorkspaceSelection({
        backendChoice: "local_shell",
        rootDir: "/",
        workspaceDir: path,
        autoWorkspaceDir: path,
      }),
    ).toEqual({ workspaceDir: path, agentId: id });
    expect(
      createWorkspaceSelection({
        backendChoice: "local_shell",
        rootDir: "/",
        workspaceDir: "/data/work",
        autoWorkspaceDir: path,
        agentId: "custom1",
      }),
    ).toEqual({ workspaceDir: "/data/work", agentId: "custom1" });
  });
});
