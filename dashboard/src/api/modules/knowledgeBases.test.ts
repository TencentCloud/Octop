import { beforeEach, describe, expect, it, vi } from "vitest";

const { request, requestUpload } = vi.hoisted(() => ({
  request: vi.fn(),
  requestUpload: vi.fn(),
}));

vi.mock("../request", () => ({ request, requestUpload }));

import { knowledgeBasesApi } from "./knowledgeBases";

beforeEach(() => {
  request.mockClear();
  requestUpload.mockClear();
});

describe("knowledgeBasesApi", () => {
  it("uses the knowledge-base capability and feature endpoints", () => {
    knowledgeBasesApi.getCapability();
    knowledgeBasesApi.setFeature({ enabled: true, model: "BAAI/bge-small" });
    knowledgeBasesApi.downloadOnnx("BAAI/bge-small-zh-v1.5");
    knowledgeBasesApi.getOnnxDownloadStatus();
    knowledgeBasesApi.activateOnnx("BAAI/bge-small-zh-v1.5");

    expect(request).toHaveBeenNthCalledWith(1, "/knowledge-bases/capability");
    expect(request).toHaveBeenNthCalledWith(2, "/knowledge-bases/feature", {
      method: "PUT",
      body: JSON.stringify({ enabled: true, model: "BAAI/bge-small" }),
    });
    expect(request).toHaveBeenNthCalledWith(
      3,
      "/knowledge-bases/onnx-download",
      {
        method: "POST",
        body: JSON.stringify({ model: "BAAI/bge-small-zh-v1.5" }),
      },
    );
    expect(request).toHaveBeenNthCalledWith(
      4,
      "/knowledge-bases/onnx-download-status",
    );
    expect(request).toHaveBeenNthCalledWith(
      5,
      "/knowledge-bases/onnx-activate",
      {
        method: "POST",
        body: JSON.stringify({ model: "BAAI/bge-small-zh-v1.5" }),
      },
    );
  });

  it("requests the full ONNX catalog when expanding embedding options", () => {
    knowledgeBasesApi.getEmbeddingOptions();
    knowledgeBasesApi.getEmbeddingOptions({ allOnnx: true });

    expect(request).toHaveBeenNthCalledWith(
      1,
      "/knowledge-bases/embedding-options",
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/knowledge-bases/embedding-options?all_onnx=true",
    );
  });

  it("uses nested document endpoints", () => {
    const file = new File(["document"], "notes.md", { type: "text/markdown" });
    knowledgeBasesApi.uploadDocument("kb-1", file);
    knowledgeBasesApi.deleteDocument("kb-1", "doc-1");
    knowledgeBasesApi.previewDocument("kb-1", "doc-1");

    expect(requestUpload).toHaveBeenCalledWith(
      "/knowledge-bases/kb-1/documents",
      expect.any(FormData),
      { method: "POST" },
      undefined,
    );
    expect(request).toHaveBeenNthCalledWith(
      1,
      "/knowledge-bases/kb-1/documents/doc-1",
      { method: "DELETE" },
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/knowledge-bases/kb-1/documents/doc-1/preview",
    );
  });

  it("forwards the upload progress handler", () => {
    const file = new File(["document"], "notes.md", { type: "text/markdown" });
    const onProgress = vi.fn();

    knowledgeBasesApi.uploadDocument("kb-1", file, "docs/notes.md", onProgress);

    expect(requestUpload).toHaveBeenCalledWith(
      "/knowledge-bases/kb-1/documents",
      expect.any(FormData),
      { method: "POST" },
      onProgress,
    );
  });
});
