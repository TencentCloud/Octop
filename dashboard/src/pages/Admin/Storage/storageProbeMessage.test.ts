import { describe, expect, it } from "vitest";

import { storageBrowseError, storageProbeMessage } from "./storageProbeMessage";

function t(key: string, options?: string | Record<string, unknown>): string {
  const catalog: Record<string, string> = {
    "storage.testFailed": "检测失败",
    "storage.browseFailed": "浏览失败",
    "storage.probe_no_such_bucket": "存储桶不存在，请检查 Bucket 名称",
    "storage.probe_write_failed": "写入探测失败：{{detail}}",
  };
  const template = catalog[key];
  if (!template) {
    if (typeof options === "string") return options;
    if (
      options &&
      typeof options === "object" &&
      typeof options.defaultValue === "string"
    ) {
      return options.defaultValue;
    }
    return key;
  }
  if (
    options &&
    typeof options === "object" &&
    typeof options.detail === "string"
  ) {
    return template.replace("{{detail}}", options.detail);
  }
  return template;
}

describe("storageProbeMessage", () => {
  it("prefers a classified bucket error over the raw SDK dump", () => {
    expect(
      storageProbeMessage(
        {
          ok: false,
          message_key: "probe_no_such_bucket",
          message:
            "The specified bucket does not exist. Check the bucket name.",
        },
        t,
        "storage.testFailed",
      ),
    ).toBe("存储桶不存在，请检查 Bucket 名称");
  });

  it("interpolates leftover write details", () => {
    expect(
      storageProbeMessage(
        {
          ok: false,
          message_key: "probe_write_failed",
          message: "widget exploded",
        },
        t,
        "storage.testFailed",
      ),
    ).toBe("写入探测失败：widget exploded");
  });
});

describe("storageBrowseError", () => {
  it("uses the classified storage key instead of WORKSPACE_OP_UNSUPPORTED", () => {
    const err = new Error(
      'Request failed: 400 - {"error":{"code":"STORAGE_BROWSE_FAILED","message":"Could not browse this storage backend.","details":{"message_key":"probe_no_such_bucket","reason":"The specified bucket does not exist. Check the bucket name."}}}',
    );
    expect(storageBrowseError(err, t as never)).toBe(
      "存储桶不存在，请检查 Bucket 名称",
    );
  });
});
