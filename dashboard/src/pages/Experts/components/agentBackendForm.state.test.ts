import { describe, expect, it } from "vitest";
import {
  backendSpecForAgentSave,
  BUILTIN_BACKENDS,
  parseBackendSpec,
} from "./agentBackendForm";

describe("expert backend choices", () => {
  it("does not offer state when creating an expert", () => {
    expect(BUILTIN_BACKENDS).not.toContain("state");
  });

  it("keeps an already saved state backend visible in the editor", () => {
    expect(parseBackendSpec({ type: "state" }).backendChoice).toBe("state");
    expect(
      parseBackendSpec({
        type: "composite",
        default: { type: "filesystem", virtual_mode: true, root_dir: "/" },
        routes: { "/tmp": { type: "state" } },
      }).pathMappings,
    ).toEqual([{ path: "/tmp", backend: "state" }]);
  });
});

describe("backendSpecForAgentSave", () => {
  const stored = {
    type: "filesystem",
    root_dir: "/",
    virtual_mode: true,
  };

  it("keeps the stored backend when a managed expert has no picker value", () => {
    expect(
      backendSpecForAgentSave("managed", stored, undefined, "local_shell", []),
    ).toBe(stored);
  });

  it("rebuilds the spec from the form for a normal expert", () => {
    expect(
      backendSpecForAgentSave(
        "expert",
        stored,
        "local_shell",
        "local_shell",
        [],
        "/data",
      ),
    ).toEqual({
      type: "local_shell",
      virtual_mode: true,
      root_dir: "/data",
    });
  });
});
