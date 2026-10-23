import { describe, expect, it } from "vitest";

import {
  isInlineDockerSpec,
  parseBackendSpec,
  buildBackendSpec,
  backendRefToSpec,
} from "./agentBackendForm";

describe("isInlineDockerSpec", () => {
  it("accepts inline docker specs", () => {
    expect(
      isInlineDockerSpec({
        type: "docker",
        image: "sb:1.0.0",
        allow_network: true,
      }),
    ).toBe(true);
  });

  it("rejects named / builtin / non-object specs", () => {
    expect(isInlineDockerSpec({ type: "named", name: "x" })).toBe(false);
    expect(isInlineDockerSpec({ type: "local_shell" })).toBe(false);
    expect(isInlineDockerSpec(null)).toBe(false);
    expect(isInlineDockerSpec("docker")).toBe(false);
  });
});

describe("inline docker spec survives the edit round-trip losslessly", () => {
  it("named refs keep their identity through parse → build", () => {
    const spec = { type: "named", name: "docker-online" };
    const parsed = parseBackendSpec(spec);
    expect(parsed.backendChoice).toBe("named:docker-online");
    expect(
      buildBackendSpec(parsed.backendChoice, "local_shell", [], "/"),
    ).toEqual(spec);
  });

  it("builtin refs round-trip", () => {
    const spec = { type: "local_shell", virtual_mode: true, root_dir: "/data" };
    const parsed = parseBackendSpec(spec);
    expect(parsed.backendChoice).toBe("local_shell");
    expect(parsed.rootDir).toBe("/data");
  });
});

describe("backendRefToSpec", () => {
  it("builds named refs", () => {
    expect(backendRefToSpec("named:foo")).toEqual({
      type: "named",
      name: "foo",
    });
  });
});
