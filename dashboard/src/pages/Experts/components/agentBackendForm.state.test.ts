import { describe, expect, it } from "vitest";
import { BUILTIN_BACKENDS, parseBackendSpec } from "./agentBackendForm";

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
