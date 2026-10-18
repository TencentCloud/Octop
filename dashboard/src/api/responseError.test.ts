import { describe, expect, it } from "vitest";
import { readErrorBody, responseError } from "./responseError";
import { apiErrorMessage, parseApiError } from "../utils/apiError";

describe("bounded response errors", () => {
  it("prefers Octop envelopes and preserves code/details for translations", async () => {
    const error = await responseError(
      new Response(
        JSON.stringify({
          error: {
            code: "PLUGIN_INSTALL_FAILED",
            message: "Install failed",
            details: { reason: "timeout" },
          },
          detail: "ignored",
        }),
        { status: 502 },
      ),
    );
    expect(error.message).toBe("Install failed");
    expect(parseApiError(error)).toEqual({
      code: "PLUGIN_INSTALL_FAILED",
      message: "Install failed",
      details: { reason: "timeout" },
    });
    expect(apiErrorMessage(error, "fallback")).toBe("Install failed");
  });
  it("never displays HTML or arbitrary text", async () => {
    const error = await responseError(
      new Response("<html>secret proxy diagnostics</html>", {
        status: 502,
        headers: { "x-request-id": "trace-123" },
      }),
    );
    expect(error.message).toBe("HTTP 502 (Request ID: trace-123)");
  });
  it("discards oversized JSON and cancels without waiting for stream cancellation", async () => {
    let cancelled = false;
    const response = new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(new Uint8Array(20000));
        },
        cancel() {
          cancelled = true;
          return new Promise(() => {});
        },
      }),
      { status: 503 },
    );
    expect(await readErrorBody(response)).toBeNull();
    expect(cancelled).toBe(true);
    expect((await responseError(response)).message).toBe("HTTP 503");
  });
  it("shares a bounded read between setup probing and error formatting", async () => {
    const response = new Response('{"detail":"Unavailable"}', { status: 503 });
    await readErrorBody(response);
    expect((await responseError(response)).message).toBe("Unavailable");
  });
});
