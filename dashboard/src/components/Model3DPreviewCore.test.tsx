import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as THREE from "three";
import { ApiResponseError } from "../api/responseError";
import Model3DPreviewCore, { parseModelBlob } from "./Model3DPreviewCore";

const webglControl = vi.hoisted(() => ({
  throwOnCreate: false,
}));

vi.mock("three", async (importOriginal) => {
  const actual = await importOriginal<typeof import("three")>();
  class MockWebGLRenderer {
    domElement: HTMLCanvasElement;
    outputColorSpace = actual.SRGBColorSpace;
    toneMapping = actual.NoToneMapping;
    toneMappingExposure = 1;
    constructor() {
      if (webglControl.throwOnCreate) {
        throw new Error("WebGL unavailable");
      }
      this.domElement = document.createElement("canvas");
    }
    setPixelRatio() {}
    setSize() {}
    render() {}
    dispose() {}
  }
  class MockPMREMGenerator {
    constructor() {}
    fromScene() {
      const texture = new actual.Texture();
      return {
        texture,
        dispose: () => texture.dispose(),
      };
    }
    dispose() {}
  }
  return {
    ...actual,
    WebGLRenderer: MockWebGLRenderer,
    PMREMGenerator: MockPMREMGenerator,
  };
});

vi.mock("three/examples/jsm/environments/RoomEnvironment.js", () => ({
  RoomEnvironment: class MockRoomEnvironment {
    dispose() {}
  },
}));

vi.mock("three/examples/jsm/controls/OrbitControls.js", () => ({
  OrbitControls: class MockOrbitControls {
    target = new THREE.Vector3();
    minDistance = 0;
    maxDistance = 100;
    enableDamping = false;
    dampingFactor = 0.05;
    autoRotate = false;
    autoRotateSpeed = 1;
    addEventListener() {}
    removeEventListener() {}
    update() {}
    dispose() {}
  },
}));

const VALID_OBJ = `v 0 0 0
v 1 0 0
v 0 1 0
f 1 2 3
`;

const VALID_ASCII_STL = `solid tri
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid tri
`;

function makeBlob(text: string, type = "text/plain"): Blob {
  const bytes = new TextEncoder().encode(text);
  const blob = new Blob([bytes], { type });
  if (typeof blob.arrayBuffer !== "function") {
    Object.defineProperty(blob, "arrayBuffer", {
      value: async () =>
        bytes.buffer.slice(
          bytes.byteOffset,
          bytes.byteOffset + bytes.byteLength,
        ),
    });
  }
  if (typeof blob.text !== "function") {
    Object.defineProperty(blob, "text", {
      value: async () => text,
    });
  }
  return blob;
}

describe("parseModelBlob", () => {
  it("parses a minimal ASCII STL blob", async () => {
    const parsed = await parseModelBlob("stl", makeBlob(VALID_ASCII_STL));
    expect(parsed.triangleCount).toBe(1);
    expect(parsed.animations).toEqual([]);
  });

  it("parses a minimal OBJ blob", async () => {
    const parsed = await parseModelBlob("obj", makeBlob(VALID_OBJ));
    expect(parsed.triangleCount).toBe(1);
  });

  it("rejects an empty OBJ blob without renderable geometry", async () => {
    await expect(
      parseModelBlob("obj", makeBlob("# empty model\n")),
    ).rejects.toThrow("Model contains no renderable geometry");
  });
});

describe("Model3DPreviewCore", () => {
  beforeEach(() => {
    webglControl.throwOnCreate = false;
  });

  it("renders fileMaybeDeleted message on 404 errors", async () => {
    const fetchBlob = vi
      .fn()
      .mockRejectedValue(
        new ApiResponseError(
          404,
          { code: "NOT_FOUND", message: "missing" },
          null,
        ),
      );
    render(
      <Model3DPreviewCore
        kind="obj"
        filename="mesh.obj"
        fetchBlob={fetchBlob}
      />,
    );

    expect(await screen.findByText("文件可能已被删除")).toBeInTheDocument();
  });

  it("recovers from error when retrying or switching fetchBlob prop", async () => {
    const failingFetch = vi.fn().mockRejectedValueOnce(new Error("network"));
    const onDownload = vi.fn();
    const { rerender } = render(
      <Model3DPreviewCore
        kind="obj"
        filename="bad.obj"
        fetchBlob={failingFetch}
        onDownload={onDownload}
      />,
    );

    expect(await screen.findByText("无法加载预览")).toBeInTheDocument();

    const retryBtn = screen.getByRole("button", { name: "重试" });
    failingFetch.mockResolvedValueOnce(makeBlob(VALID_OBJ));
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(screen.getByText("OBJ")).toBeInTheDocument();
    });

    // Trigger another error, then recover by swapping the fetchBlob prop
    // (regression test for keeping hostRef mounted across error states).
    const brokenFetch = vi.fn().mockRejectedValue(new Error("boom"));
    rerender(
      <Model3DPreviewCore
        kind="obj"
        filename="broken.obj"
        fetchBlob={brokenFetch}
        onDownload={onDownload}
      />,
    );
    expect(await screen.findByText("无法加载预览")).toBeInTheDocument();

    const okFetch = vi.fn().mockResolvedValue(makeBlob(VALID_OBJ));
    rerender(
      <Model3DPreviewCore
        kind="obj"
        filename="good.obj"
        fetchBlob={okFetch}
        onDownload={onDownload}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText("OBJ")).toBeInTheDocument();
      expect(screen.queryByText("无法加载预览")).toBeNull();
    });
  });

  it("shows WebGL unavailable message and download button when WebGLRenderer throws", async () => {
    webglControl.throwOnCreate = true;
    const fetchBlob = vi.fn().mockResolvedValue(makeBlob(VALID_OBJ));
    const onDownload = vi.fn();
    render(
      <Model3DPreviewCore
        kind="obj"
        filename="mesh.obj"
        fetchBlob={fetchBlob}
        onDownload={onDownload}
      />,
    );

    expect(
      await screen.findByText(
        "当前环境不支持 WebGL 3D 渲染，请下载模型后使用本地软件查看",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "common.download" }));
    expect(onDownload).toHaveBeenCalledTimes(1);
  });
});
