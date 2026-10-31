import { describe, expect, it } from "vitest";
import { backendFlagIcon, resolveBackendFlag } from "./backendFlag";

const catalog = [
  { name: "prod-cos-bucket", kind: "cos" },
  { name: "lab-docker", kind: "docker" },
];

describe("resolveBackendFlag", () => {
  it("uses the local shell mark when a local expert has no backend spec", () => {
    expect(resolveBackendFlag(undefined, catalog)).toEqual({
      logoKind: "shell",
      fallback: null,
      labelKey: "experts.backendModes.localShell",
      labelText: null,
    });
  });

  it("hides the mark when a remote expert has no backend spec", () => {
    expect(
      resolveBackendFlag(undefined, catalog, { assumeDefault: false }),
    ).toBeNull();
  });

  it("maps built-in modes to a brand or a fallback icon", () => {
    expect(resolveBackendFlag({ type: "filesystem" }, [])).toMatchObject({
      logoKind: "filesystem",
      labelKey: "experts.backendModes.filesystem",
    });
    expect(resolveBackendFlag({ type: "state" }, [])).toMatchObject({
      logoKind: null,
      fallback: "state",
    });
    expect(
      resolveBackendFlag(
        {
          type: "composite",
          default: { type: "local_shell" },
          routes: {},
        },
        [],
      ),
    ).toMatchObject({ fallback: "composite" });
  });

  it("uses the storage kind icon and keeps the configured name for the tooltip", () => {
    expect(
      resolveBackendFlag({ type: "named", name: "prod-cos-bucket" }, catalog),
    ).toEqual({
      logoKind: "cos",
      fallback: null,
      labelKey: null,
      labelText: "prod-cos-bucket",
    });
  });

  it("groups object stores and sandboxes onto two icons", () => {
    expect(
      backendFlagIcon(resolveBackendFlag({ type: "local_shell" }, [])!),
    ).toBe("shell");
    expect(
      backendFlagIcon(resolveBackendFlag({ type: "filesystem" }, [])!),
    ).toBe("filesystem");
    expect(
      backendFlagIcon(
        resolveBackendFlag(
          { type: "named", name: "prod-cos-bucket" },
          catalog,
        )!,
      ),
    ).toBe("storage");
    expect(
      backendFlagIcon(
        resolveBackendFlag({ type: "named", name: "oss-bucket" }, [
          { name: "oss-bucket", kind: "oss" },
        ])!,
      ),
    ).toBe("storage");
    expect(
      backendFlagIcon(
        resolveBackendFlag({ type: "named", name: "lab-docker" }, catalog)!,
      ),
    ).toBe("sandbox");
    expect(
      backendFlagIcon(
        resolveBackendFlag({ type: "named", name: "db" }, [
          { name: "db", kind: "postgres" },
        ])!,
      ),
    ).toBe("database");
    expect(
      backendFlagIcon(
        resolveBackendFlag(
          {
            type: "composite",
            default: { type: "local_shell" },
            routes: {},
          },
          [],
        )!,
      ),
    ).toBe("composite");
  });

  it("falls back to a generic icon when the named backend is unknown", () => {
    expect(
      resolveBackendFlag({ type: "named", name: "gone-backend" }, catalog),
    ).toEqual({
      logoKind: null,
      fallback: "generic",
      labelKey: null,
      labelText: "gone-backend",
    });
  });
});
