import { describe, expect, it, vi } from "vitest";
import { openDesignApi } from "./openDesign";
import { requestStream } from "../request";
vi.mock("../request", () => ({ request: vi.fn(), requestStream: vi.fn() }));

describe("OpenDesign live task snapshots", () => {
  it("reassembles split UTF-8 SSE frames and ignores heartbeats", async () => {
    const frames = [
      'data: [{"task_id":"一号","status":"running"}]\n\n: keepalive\n\n',
      'data: [{"task_id":"一号","status":"succeeded"}]\n\n',
    ];
    const bytes = new TextEncoder().encode(frames.join(""));
    vi.mocked(requestStream).mockResolvedValue({
      body: new ReadableStream({
        start(controller) {
          for (let i = 0; i < bytes.length; i += 7)
            controller.enqueue(bytes.slice(i, i + 7));
          controller.close();
        },
      }),
    } as Awaited<ReturnType<typeof requestStream>>);
    const onTasks = vi.fn();
    await openDesignApi.watch(
      "agent",
      "thread",
      onTasks,
      new AbortController().signal,
    );
    expect(onTasks.mock.calls).toEqual([
      [[{ task_id: "一号", status: "running" }]],
      [[{ task_id: "一号", status: "succeeded" }]],
    ]);
  });
});
