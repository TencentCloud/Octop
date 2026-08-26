import { describe, expect, it } from "vitest";

import {
  DEFAULT_MAX_UPLOAD_BYTES,
  applyUploadLimitFetchResult,
} from "./useServerUploadLimit";

describe("applyUploadLimitFetchResult", () => {
  it("does not cache a failed fetch so the next mount can retry", () => {
    const result = applyUploadLimitFetchResult({ ok: false });
    expect(result.value).toBe(DEFAULT_MAX_UPLOAD_BYTES);
    expect(result.cache).toBeNull();
  });

  it("caches a successful limit from the server", () => {
    const bytes = 50 * 1024 * 1024;
    const result = applyUploadLimitFetchResult({ ok: true, bytes });
    expect(result.value).toBe(bytes);
    expect(result.cache).toBe(bytes);
  });
});
