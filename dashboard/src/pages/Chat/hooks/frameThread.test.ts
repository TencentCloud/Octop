import { describe, expect, it } from "vitest";
import { frameBelongsToThread } from "./frameThread";

describe("frameBelongsToThread", () => {
  it("accepts frames with no thread_id", () => {
    expect(frameBelongsToThread({ type: "pong" }, "thr-a")).toBe(true);
  });

  it("accepts matching thread_id", () => {
    expect(
      frameBelongsToThread({ type: "token", thread_id: "thr-a" }, "thr-a"),
    ).toBe(true);
  });

  it("rejects a different thread_id", () => {
    expect(
      frameBelongsToThread({ type: "token", thread_id: "thr-b" }, "thr-a"),
    ).toBe(false);
  });
});
