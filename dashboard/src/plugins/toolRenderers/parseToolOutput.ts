import type { OctopUiHint, ParsedToolOutput } from "./types";

function asOctopUi(value: unknown): OctopUiHint | undefined {
  if (!value || typeof value !== "object") return undefined;
  const obj = value as Record<string, unknown>;
  const renderer = typeof obj.renderer === "string" ? obj.renderer.trim() : "";
  if (!renderer) return undefined;
  const version =
    typeof obj.version === "number" && Number.isFinite(obj.version)
      ? obj.version
      : undefined;
  return version === undefined ? { renderer } : { renderer, version };
}

/**
 * Parse tool ``output`` for the ``octop_ui`` envelope.
 * Accepts a JSON string or an already-parsed object.
 */
export function parseOctopToolOutput(output: unknown): ParsedToolOutput {
  if (output === undefined || output === null || output === "") {
    return {
      isJson: false,
      raw: output,
      text: typeof output === "string" ? output : undefined,
    };
  }

  if (typeof output === "object") {
    if (Array.isArray(output)) {
      return { isJson: true, raw: output };
    }
    const obj = output as Record<string, unknown>;
    return {
      isJson: true,
      raw: output,
      octopUi: asOctopUi(obj.octop_ui),
      data: "data" in obj ? obj.data : undefined,
      text: typeof obj.text === "string" ? obj.text : undefined,
    };
  }

  if (typeof output !== "string") {
    return { isJson: false, raw: output, text: String(output) };
  }

  try {
    const raw = JSON.parse(output) as unknown;
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return {
        isJson: true,
        raw,
        text: typeof raw === "string" ? raw : undefined,
      };
    }
    const obj = raw as Record<string, unknown>;
    const octopUi = asOctopUi(obj.octop_ui);
    const text = typeof obj.text === "string" ? obj.text : undefined;
    const data = "data" in obj ? obj.data : undefined;
    return { isJson: true, raw, octopUi, data, text };
  } catch {
    return { isJson: false, raw: output, text: output };
  }
}

/** Rebuild a JSON output string after L2 ``patchResult`` on ``data``. */
export function mergePatchedToolOutput(
  previousOutput: string | undefined,
  nextData: unknown,
): string {
  const parsed = parseOctopToolOutput(previousOutput);
  if (parsed.isJson && parsed.raw && typeof parsed.raw === "object") {
    const base = { ...(parsed.raw as Record<string, unknown>) };
    base.data = nextData;
    return JSON.stringify(base);
  }
  if (typeof nextData === "string") {
    return nextData;
  }
  try {
    return JSON.stringify(nextData);
  } catch {
    return String(nextData);
  }
}
