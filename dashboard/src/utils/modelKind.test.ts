import { describe, expect, it } from "vitest";
import { getModelKind } from "./modelKind";

describe("getModelKind", () => {
  it("recognizes supported 3D model extensions case-insensitively", () => {
    expect(getModelKind("generated/3d/mesh.glb")).toBe("glb");
    expect(getModelKind("MESH.GLB")).toBe("glb");
    expect(getModelKind("/work/scene.gltf")).toBe("gltf");
    expect(getModelKind("part.stl")).toBe("stl");
    expect(getModelKind("model.OBJ")).toBe("obj");
    expect(getModelKind("rig.fbx")).toBe("fbx");
  });

  it("ignores query/hash suffixes and rejects unsupported files", () => {
    expect(getModelKind("mesh.glb?download=1#top")).toBe("glb");
    expect(getModelKind("archive.zip")).toBeNull();
    expect(getModelKind("preview.png")).toBeNull();
    expect(getModelKind("mesh.usdz")).toBeNull();
    expect(getModelKind(".glb")).toBeNull();
    expect(getModelKind("README")).toBeNull();
  });
});
