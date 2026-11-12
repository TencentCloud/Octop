import { describe, expect, it } from "vitest";
import { ApiResponseError } from "../api/responseError";
import {
  hasProcessRestarted,
  shouldPollAfterRestartError,
} from "./useServiceRestart";

describe("hasProcessRestarted", () => {
  it("returns true when started_at changes", () => {
    expect(hasProcessRestarted(100, 200)).toBe(true);
  });

  it("returns false when started_at is missing or unchanged", () => {
    expect(hasProcessRestarted(undefined, 200)).toBe(false);
    expect(hasProcessRestarted(100, undefined)).toBe(false);
    expect(hasProcessRestarted(100, 100)).toBe(false);
  });
});

describe("shouldPollAfterRestartError", () => {
  it.each([502, 503, 504])("polls after HTTP %i", (status) => {
    expect(
      shouldPollAfterRestartError(new ApiResponseError(status, null, null)),
    ).toBe(true);
  });

  it.each([400, 403, 409, 500])("does not poll after HTTP %i", (status) => {
    expect(
      shouldPollAfterRestartError(new ApiResponseError(status, null, null)),
    ).toBe(false);
  });

  it("keeps polling for network errors without an HTTP response", () => {
    expect(shouldPollAfterRestartError(new Error("Failed to fetch"))).toBe(
      true,
    );
  });
});
