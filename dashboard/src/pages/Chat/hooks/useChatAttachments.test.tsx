import { act, renderHook, waitFor } from "@testing-library/react";
import type { DragEvent } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { message } from "@/utils/antdMessage";
import { uploadFile } from "../../../api/modules/upload";
import { DESKTOP_FILE_DROP_EVENT } from "../../../utils/desktopFileDrop";
import { useChatAttachments } from "./useChatAttachments";

vi.mock("../../../hooks/useServerUploadLimit", () => ({
  useServerUploadLimit: () => ({ maxUploadBytes: 1024, maxUploadMb: 1 }),
}));

vi.mock("../../../api/modules/upload", () => ({
  uploadFile: vi.fn(),
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), warning: vi.fn() },
}));

function dragEvent(
  init: Partial<DragEvent<HTMLElement>> & { currentTarget?: HTMLElement },
): DragEvent<HTMLElement> {
  return {
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
    dataTransfer: { types: ["Files"], items: [], files: [] },
    relatedTarget: null,
    ...init,
  } as unknown as DragEvent<HTMLElement>;
}

describe("useChatAttachments drop", () => {
  beforeEach(() => {
    vi.mocked(uploadFile).mockReset();
    vi.mocked(message.error).mockReset();
    vi.mocked(message.warning).mockReset();
    vi.mocked(uploadFile).mockImplementation(async (_agentId, file) => ({
      path: `inbound/${file.name}`,
      workspace_path: `inbound/${file.name}`,
      filename: file.name,
      media_type: file.type || "application/octet-stream",
      url: "",
      access_url: `/files/${file.name}`,
    }));
  });

  it("uploads every file from one drop", async () => {
    const { result } = renderHook(() => useChatAttachments("agent-1"));
    const first = new File(["a"], "a.txt", { type: "text/plain" });
    const second = new File(["b"], "b.txt", { type: "text/plain" });
    const dropped = dragEvent({
      dataTransfer: {
        types: ["Files"],
        items: [
          { kind: "file", getAsFile: () => first },
          { kind: "file", getAsFile: () => second },
        ],
        files: [first, second],
      } as unknown as DataTransfer,
    });

    await act(async () => {
      await result.current.handleDrop(dropped);
    });

    await waitFor(() => {
      expect(result.current.attachments.map((item) => item.filename)).toEqual([
        "a.txt",
        "b.txt",
      ]);
    });
    expect(uploadFile).toHaveBeenCalledTimes(2);
    expect(result.current.dragOver).toBe(false);
  });

  it("keeps the drop highlight while the pointer is still inside the composer", () => {
    const { result } = renderHook(() => useChatAttachments("agent-1"));
    const shell = document.createElement("div");
    const field = document.createElement("textarea");
    shell.appendChild(field);

    act(() => {
      result.current.handleDragEnter(
        dragEvent({
          currentTarget: shell,
          dataTransfer: { types: ["Files"] } as DataTransfer,
        }),
      );
    });
    expect(result.current.dragOver).toBe(true);

    act(() => {
      result.current.handleDragLeave(
        dragEvent({ currentTarget: shell, relatedTarget: field }),
      );
    });
    expect(result.current.dragOver).toBe(true);

    act(() => {
      result.current.handleDragLeave(
        dragEvent({ currentTarget: shell, relatedTarget: document.body }),
      );
    });
    expect(result.current.dragOver).toBe(false);
  });

  it("does not highlight a text drag", () => {
    const { result } = renderHook(() => useChatAttachments("agent-1"));
    const event = dragEvent({
      dataTransfer: {
        types: ["text/plain"],
        items: [],
        files: [],
      } as unknown as DataTransfer,
    });

    act(() => {
      result.current.handleDragEnter(event);
    });

    expect(result.current.dragOver).toBe(false);
    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it("warns when a dropped folder has no files", async () => {
    const { result } = renderHook(() => useChatAttachments("agent-1"));
    const emptyDir = {
      isFile: false,
      isDirectory: true,
      name: "empty",
      fullPath: "/empty",
      createReader: () => ({
        readEntries(success: (entries: FileSystemEntry[]) => void) {
          success([]);
        },
      }),
    };
    const dropped = dragEvent({
      dataTransfer: {
        types: ["Files"],
        items: [
          {
            kind: "file",
            webkitGetAsEntry: () => emptyDir,
            getAsFile: () => null,
          },
        ],
        files: [],
      } as unknown as DataTransfer,
    });

    await act(async () => {
      await result.current.handleDrop(dropped);
    });

    expect(uploadFile).not.toHaveBeenCalled();
    expect(message.warning).toHaveBeenCalledWith("No files to upload");
  });

  it("uploads files delivered by the desktop shell", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("note", {
            status: 200,
            headers: { "Content-Type": "text/plain" },
          }),
      ),
    );
    const { result } = renderHook(() => useChatAttachments("agent-1"));

    await act(async () => {
      window.dispatchEvent(
        new CustomEvent(DESKTOP_FILE_DROP_EVENT, {
          detail: {
            files: [
              {
                name: "note.txt",
                url: "http://127.0.0.1:9/drop/token/0",
                type: "text/plain",
              },
            ],
            truncated: true,
            max: 500,
          },
        }),
      );
    });

    await waitFor(() => {
      expect(result.current.attachments.map((item) => item.filename)).toEqual([
        "note.txt",
      ]);
    });
    expect(uploadFile).toHaveBeenCalledTimes(1);
    expect(message.warning).toHaveBeenCalledWith(
      "Only the first 500 files can be uploaded at once",
    );
    expect(result.current.dragOver).toBe(false);
    vi.unstubAllGlobals();
  });
});
