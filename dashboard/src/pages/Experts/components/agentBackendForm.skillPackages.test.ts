import { describe, expect, it } from "vitest";
import {
  isHostRootDir,
  normalizeRootDir,
  supportsHostSkillPackages,
  supportsHostSkillPackagesFromConfig,
} from "./agentBackendForm";

describe("skill package backend gates", () => {
  it("normalizes host root sentinels", () => {
    expect(normalizeRootDir(undefined)).toBe("/");
    expect(normalizeRootDir("")).toBe("/");
    expect(normalizeRootDir("/")).toBe("/");
    expect(normalizeRootDir("/tmp/project/")).toBe("/tmp/project");
    expect(isHostRootDir("/")).toBe(true);
    expect(isHostRootDir("/tmp/project")).toBe(false);
  });

  it("allows local backends with host root", () => {
    expect(
      supportsHostSkillPackages({
        backendChoice: "local_shell",
        rootDir: "/",
      }),
    ).toBe(true);
    expect(
      supportsHostSkillPackages({
        backendChoice: "filesystem",
        rootDir: "/",
      }),
    ).toBe(true);
  });

  it("allows workspace-scoped root when paths match", () => {
    expect(
      supportsHostSkillPackages({
        backendChoice: "local_shell",
        rootDir: "/home/u/.octop/agents/A1",
        workspaceDir: "/home/u/.octop/agents/A1/",
      }),
    ).toBe(true);
  });

  it("rejects scoped project roots and non-local backends", () => {
    expect(
      supportsHostSkillPackages({
        backendChoice: "local_shell",
        rootDir: "/home/u/project",
      }),
    ).toBe(false);
    expect(
      supportsHostSkillPackages({
        backendChoice: "local_shell",
        rootDir: "/home/u/project",
        workspaceDir: "/home/u/project/.octop/workspaces/A1",
      }),
    ).toBe(false);
    expect(
      supportsHostSkillPackages({
        backendChoice: "state",
        rootDir: "/",
      }),
    ).toBe(false);
    expect(
      supportsHostSkillPackages({
        backendChoice: "composite",
        rootDir: "/",
      }),
    ).toBe(false);
  });

  it("reads support from agent config", () => {
    expect(
      supportsHostSkillPackagesFromConfig({
        backend: { type: "local_shell", root_dir: "/", virtual_mode: true },
      }),
    ).toBe(true);
    expect(
      supportsHostSkillPackagesFromConfig({
        backend: {
          type: "local_shell",
          root_dir: "/tmp/project",
          virtual_mode: true,
        },
      }),
    ).toBe(false);
  });
});
