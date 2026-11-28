import { describe, expect, it } from "vitest";
import {
  agentAttachmentAccessUrl,
  agentMediaPreviewUrl,
  canonicalizeMediaApiUrl,
  collectToolMediaFromToolData,
  isHostAbsoluteMediaPath,
  isMediaPushTool,
  needsAuthBlobFetch,
  parseStructuredToolOutput,
  parseToolExecutionFeedback,
  toMediaPreviewSource,
  workspaceDownloadUrl,
} from "./toolMediaBlocks";

describe("workspaceDownloadUrl", () => {
  it("keeps host-absolute paths as-is", () => {
    const url = workspaceDownloadUrl("main", "/Users/me/Desktop/a.pptx");
    expect(url).toContain("path=%2FUsers%2Fme%2FDesktop%2Fa.pptx");
  });

  it("rewrites legacy /outbound/… to relative workspace keys", () => {
    const url = workspaceDownloadUrl("main", "/outbound/chart.png");
    expect(url).toContain("path=outbound%2Fchart.png");
    expect(url).not.toContain("path=%2Foutbound");
  });

  it("passes relative outbound without adding a slash", () => {
    const url = workspaceDownloadUrl("main", "outbound/chart.png");
    expect(url).toContain("path=outbound%2Fchart.png");
  });
});

describe("canonicalizeMediaApiUrl", () => {
  it("rewrites stored download links with /outbound/ path", () => {
    const raw =
      "/api/agents/main/workspace/download?path=%2Foutbound%2Fchart.png";
    const next = canonicalizeMediaApiUrl(raw);
    expect(next).toContain("path=outbound%2Fchart.png");
    expect(next).not.toContain("path=%2Foutbound");
  });
});

describe("isHostAbsoluteMediaPath", () => {
  it("treats /outbound as workspace key, not host abs", () => {
    expect(isHostAbsoluteMediaPath("/outbound/a.png")).toBe(false);
    expect(isHostAbsoluteMediaPath("/Users/me/a.png")).toBe(true);
  });
});

describe("toMediaPreviewSource", () => {
  it("does not wrap workspace tree keys as host file:// paths", () => {
    expect(
      toMediaPreviewSource("/octop-logo.png", {
        agentId: "ED7N8B",
        fromWorkspace: true,
      }),
    ).toBe("octop-logo.png");
    expect(
      toMediaPreviewSource("/generated/slide.png", { fromWorkspace: true }),
    ).toBe("generated/slide.png");
  });

  it("keeps agent-home host abs as file:// for chat/tools (virtual failback)", () => {
    expect(
      toMediaPreviewSource("/Users/me/.octop/agents/ED7N8B/octop-logo.png", {
        agentId: "ED7N8B",
      }),
    ).toBe("file:///Users/me/.octop/agents/ED7N8B/octop-logo.png");
    expect(
      toMediaPreviewSource("file:///tmp/x/outbound/chart.png", {
        agentId: "main",
      }),
    ).toBe("outbound/chart.png");
  });

  it("keeps real host temps as file:// when not inside agent home", () => {
    expect(toMediaPreviewSource("/Users/me/Desktop/a.png")).toBe(
      "file:///Users/me/Desktop/a.png",
    );
  });

  it("feeds agentMediaPreviewUrl file:// for agent-home pngs from chat", () => {
    const url = agentMediaPreviewUrl(
      "ED7N8B",
      "/Users/me/.octop/agents/ED7N8B/octop-logo.png",
      "image/png",
    );
    expect(url).toContain("source=file");
    expect(url).toContain("octop-logo.png");
  });
});

describe("needsAuthBlobFetch", () => {
  it("requires auth for uploaded expert avatars", () => {
    expect(needsAuthBlobFetch("/api/agents/agt_1/avatar")).toBe(true);
    expect(needsAuthBlobFetch("/api/agents/agt_1/avatar?v=9")).toBe(true);
    expect(needsAuthBlobFetch("/api/experts/published/pexp_1/avatar")).toBe(
      true,
    );
    expect(needsAuthBlobFetch("/api/experts/published/pexp_1/avatar?v=9")).toBe(
      true,
    );
    expect(needsAuthBlobFetch("https://cdn.example.com/icon.png")).toBe(false);
    expect(needsAuthBlobFetch("/api/plugins/weather/ui/icon.svg")).toBe(true);
    expect(needsAuthBlobFetch("/api/plugins/market/weather/ui/icon.svg")).toBe(
      true,
    );
    expect(needsAuthBlobFetch("/api/plugins/weather/ui/dist/index.js")).toBe(
      false,
    );
  });
});

describe("parseStructuredToolOutput", () => {
  it("renders WorkBuddy image generation envelopes from workspace paths", () => {
    const parsed = parseStructuredToolOutput(
      JSON.stringify({
        type: "image_gen_tool_result",
        images: [
          {
            path: "generated/images/a.png",
            localPath: "/private/a.png",
            mediaType: "image/png",
          },
        ],
      }),
      "agent-1",
    );

    expect(parsed.images).toHaveLength(1);
    expect(parsed.images[0].url).toContain("/api/agents/agent-1/media/preview");
    expect(parsed.images[0].url).toContain("generated%2Fimages%2Fa.png");
  });

  it("keeps actionable feedback when a generation envelope has no media", () => {
    const output = JSON.stringify({
      schema_version: 1,
      type: "image_gen_tool_result",
      status: "failed",
      is_error: true,
      message: "The configured image model is not enabled.",
      error: {
        code: "model_access_required",
        retryable: false,
        safe_to_resubmit: false,
      },
      remediation: { action: "configure_model" },
      execution: { provider: "volcengine_ark", model: "seedream" },
      images: [],
    });

    const parsed = parseStructuredToolOutput(output, "agent-1");
    expect(parsed.images).toEqual([]);
    expect(parsed.textOutput).toBe(
      "The configured image model is not enabled.",
    );
    expect(parsed.feedback).toMatchObject({
      isError: true,
      code: "model_access_required",
      action: "configure_model",
      retryable: false,
      safeToResubmit: false,
      provider: "volcengine_ark",
      model: "seedream",
    });
  });

  it("parses deferred tool activation feedback for the model and UI", () => {
    const feedback = parseToolExecutionFeedback(
      JSON.stringify({
        schema_version: 1,
        type: "tool_activation_error",
        status: "failed",
        is_error: true,
        message: "Tool schema was not loaded.",
        error: { code: "tool_schema_not_loaded", retryable: true },
        remediation: { action: "retry_with_loaded_schema" },
      }),
    );

    expect(feedback).toMatchObject({
      isError: true,
      code: "tool_schema_not_loaded",
      action: "retry_with_loaded_schema",
      retryable: true,
    });
  });
});

describe("agentAttachmentAccessUrl", () => {
  it("uses media preview for images, video, and audio", () => {
    expect(
      agentAttachmentAccessUrl("a1", "inbound/x.png", "image/png"),
    ).toContain("/media/preview?");
    expect(
      agentAttachmentAccessUrl("a1", "inbound/x.mp4", "video/mp4"),
    ).toContain("/media/preview?");
    expect(
      agentAttachmentAccessUrl("a1", "inbound/x.mp3", "audio/mpeg"),
    ).toContain("/media/preview?");
    expect(
      agentAttachmentAccessUrl("a1", "inbound/x.pdf", "application/pdf"),
    ).toContain("/workspace/download?");
  });
});

describe("collectToolMediaFromToolData", () => {
  it("matches backend delivery tool allowlist", () => {
    expect(isMediaPushTool("send_file_to_user")).toBe(true);
    expect(isMediaPushTool("namespace/desktop_screenshot")).toBe(true);
    expect(isMediaPushTool("generate_image")).toBe(true);
    expect(isMediaPushTool("ls")).toBe(false);
    expect(isMediaPushTool("read_file")).toBe(false);
    expect(isMediaPushTool("browser_use")).toBe(false);
  });

  it("ignores plain-text and argument image paths for non-delivery tools", () => {
    const lsMedia = collectToolMediaFromToolData(
      {
        name: "ls",
        arguments: JSON.stringify({ path: "inbound" }),
        output: "/Users/alice/.octop/agents/A1/inbound/1795000000_old.png",
      },
      "A1",
    );
    expect(lsMedia.images).toEqual([]);

    const readMedia = collectToolMediaFromToolData(
      {
        name: "read_file",
        arguments: JSON.stringify({ file_path: "inbound/1795000000_old.png" }),
        output: "Read image metadata",
      },
      "A1",
    );
    expect(readMedia.images).toEqual([]);
  });

  it("keeps plain-text and argument inference for delivery tools", () => {
    const shotMedia = collectToolMediaFromToolData(
      {
        name: "desktop_screenshot",
        output:
          "Screenshot saved to /Users/alice/.octop/agents/A1/outbound/screen.png",
      },
      "A1",
    );
    expect(shotMedia.images).toHaveLength(1);
    expect(shotMedia.images[0].filename).toBe("screen.png");

    const sendMedia = collectToolMediaFromToolData(
      {
        name: "send_file_to_user",
        arguments: JSON.stringify({ file_path: "outbound/chart.png" }),
        output: "Sent file",
      },
      "A1",
    );
    expect(sendMedia.images).toHaveLength(1);
    expect(sendMedia.images[0].filename).toBe("chart.png");
  });
});
