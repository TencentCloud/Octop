import type { ParsedApiError } from "../utils/apiError";

const MAX_ERROR_BYTES = 16 * 1024;
const bodies = new WeakMap<Response, Promise<unknown>>();

/** Consume a failed response once, with bounds on both bytes and waiting time. */
export function readErrorBody(response: Response): Promise<unknown> {
  let body = bodies.get(response);
  if (!body) {
    body = (async () => {
      const reader = response.body?.getReader();
      if (!reader) return null;
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        const read = async () => {
          const decoder = new TextDecoder();
          let text = "";
          let size = 0;
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            size += value.byteLength;
            if (size > MAX_ERROR_BYTES) return null;
            text += decoder.decode(value, { stream: true });
          }
          text += decoder.decode();
          try {
            return JSON.parse(text) as unknown;
          } catch {
            return null;
          }
        };
        return await Promise.race([
          read(),
          new Promise<null>((resolve) => {
            timer = setTimeout(() => resolve(null), 2000);
          }),
        ]);
      } catch {
        return null;
      } finally {
        clearTimeout(timer);
        void reader.cancel().catch(() => {});
      }
    })();
    bodies.set(response, body);
  }
  return body;
}

export class ApiResponseError extends Error {
  readonly status: number;
  readonly apiError: ParsedApiError | null;
  constructor(
    status: number,
    apiError: ParsedApiError | null,
    requestId: string | null,
  ) {
    super(
      apiError?.message ||
        `HTTP ${status}${
          requestId ? ` (Request ID: ${requestId.slice(0, 128)})` : ""
        }`,
    );
    this.status = status;
    this.apiError = apiError;
    this.name = "ApiResponseError";
  }
}

export async function responseError(
  response: Response,
): Promise<ApiResponseError> {
  const body = await readErrorBody(response);
  let parsed: ParsedApiError | null = null;
  if (body && typeof body === "object") {
    const data = body as Record<string, unknown>;
    const envelope = data.error;
    if (envelope && typeof envelope === "object") {
      const error = envelope as Record<string, unknown>;
      parsed = {
        code: typeof error.code === "string" ? error.code : undefined,
        message: typeof error.message === "string" ? error.message : undefined,
        details:
          error.details && typeof error.details === "object"
            ? (error.details as Record<string, unknown>)
            : undefined,
      };
    } else {
      const message = data.detail ?? data.message;
      if (typeof message === "string") parsed = { message };
    }
  }
  return new ApiResponseError(
    response.status,
    parsed,
    response.headers.get("x-request-id") ??
      response.headers.get("x-octop-request-id"),
  );
}
