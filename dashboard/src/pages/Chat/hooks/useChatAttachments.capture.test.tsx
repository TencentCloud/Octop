import { buildUserMessageContent } from "../utils/chatAttachments";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  captureNativeAttachment,
  nativeCaptureAvailability,
} from "../../../api/modules/upload";
import { useChatAttachments } from "./useChatAttachments";

vi.mock("../../../api/modules/upload", () => ({
  uploadFile: vi.fn(),
  nativeCaptureAvailability: vi.fn(),
  captureNativeAttachment: vi.fn(),
}));
vi.mock("../../../hooks/useServerUploadLimit", () => ({
  useServerUploadLimit: () => ({ maxUploadBytes: 10485760, maxUploadMb: 10 }),
}));
vi.mock("@/utils/antdMessage", () => ({ message: { error: vi.fn() } }));

const captured = {
  status: "ok" as const,
  attachments: [
    {
      path: "inbound/scan.pdf",
      workspace_path: "inbound/scan.pdf",
      filename: "scan.pdf",
      media_type: "application/pdf",
      url: "/preview",
      access_url: "/preview",
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(nativeCaptureAvailability).mockResolvedValue({
    available: true,
  });
});

describe("composer native capture", () => {
  it("adds a captured report to pending attachments", async () => {
    vi.mocked(captureNativeAttachment).mockResolvedValue(captured);
    const { result } = renderHook(() =>
      useChatAttachments("agent-a", "thread-a"),
    );
    await waitFor(() =>
      expect(result.current.nativeCaptureAvailable).toBe(true),
    );
    await act(() => result.current.handleNativeCapture());
    expect(captureNativeAttachment).toHaveBeenCalledWith("agent-a", "scan");
    expect(result.current.attachments).toEqual([
      {
        url: "/preview",
        filename: "scan.pdf",
        mediaType: "application/pdf",
        workspacePath: "inbound/scan.pdf",
        kind: "file",
      },
    ]);
    expect(result.current.capturing).toBe(false);
    expect(
      buildUserMessageContent("Read this", result.current.attachments),
    ).toEqual([
      { type: "text", text: "Read this" },
      {
        type: "file",
        filename: "scan.pdf",
        media_type: "application/pdf",
        workspace_path: "inbound/scan.pdf",
      },
    ]);
  });

  it("does not attach a late result to another chat", async () => {
    let resolve!: (value: typeof captured) => void;
    vi.mocked(captureNativeAttachment).mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const { result, rerender } = renderHook(
      ({ thread }) => useChatAttachments("agent-a", thread),
      { initialProps: { thread: "thread-a" } },
    );
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.handleNativeCapture();
    });
    expect(result.current.capturing).toBe(true);
    rerender({ thread: "thread-b" });
    await act(async () => {
      resolve(captured);
      await pending;
    });
    expect(result.current.attachments).toEqual([]);
  });

  it("keeps cancellation quiet and empty", async () => {
    vi.mocked(captureNativeAttachment).mockResolvedValue({
      status: "cancelled",
      attachments: [],
    });
    const { result } = renderHook(() => useChatAttachments("agent-a"));
    await act(() => result.current.handleNativeCapture());
    expect(result.current.attachments).toEqual([]);
  });
});

it("keeps the PDF reference and a separate scan thumbnail", async () => {
  vi.mocked(captureNativeAttachment).mockResolvedValue({
    ...captured,
    attachments: [
      { ...captured.attachments[0], preview_url: "/scan-thumbnail" },
    ],
  });
  const { result } = renderHook(() =>
    useChatAttachments("agent-a", "thread-a"),
  );
  await act(() => result.current.handleNativeCapture());
  expect(result.current.attachments[0]).toMatchObject({
    url: "/preview",
    previewUrl: "/scan-thumbnail",
    mediaType: "application/pdf",
  });
});

it("sends a captured photo through the existing image message builder", async () => {
  vi.mocked(captureNativeAttachment).mockResolvedValue({
    status: "ok",
    attachments: [
      {
        ...captured.attachments[0],
        filename: "photo.png",
        media_type: "image/png",
        path: "inbound/photo.png",
        workspace_path: "inbound/photo.png",
      },
    ],
  });
  const { result } = renderHook(() =>
    useChatAttachments("agent-a", "thread-a"),
  );
  await act(() => result.current.handleNativeCapture("photo"));
  expect(
    buildUserMessageContent("Organize this", result.current.attachments),
  ).toEqual([
    { type: "text", text: "Organize this" },
    expect.objectContaining({
      type: "image",
      workspace_path: "inbound/photo.png",
      filename: "photo.png",
    }),
  ]);
});
