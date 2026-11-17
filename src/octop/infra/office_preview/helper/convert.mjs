#!/usr/bin/env node
/**
 * Short-lived LibreOffice Kit helper. Reads argv paths only — never URLs.
 * Stdout is a JSON object; stderr is discarded by the Python parent.
 */
import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";

const inputPath = process.argv[2];
const outputPath = process.argv[3];
if (!inputPath || !outputPath) {
  process.stdout.write(JSON.stringify({ ok: false, error: "usage" }));
  process.exit(2);
}

function missingFontsFrom(result) {
  if (!result || typeof result !== "object") return [];
  const raw = result.missingFonts ?? result.missing_fonts ?? [];
  if (!Array.isArray(raw)) return [];
  return raw.filter((name) => typeof name === "string" && name.trim());
}

let converter;
try {
  const kit = await import("@deepseek-ai/libreoffice-kit");
  const createConverter =
    kit.createConverter ?? kit.default?.createConverter ?? kit.default;
  if (typeof createConverter !== "function") {
    throw new Error("createConverter missing");
  }
  converter = await createConverter();
  await mkdir(dirname(outputPath), { recursive: true });
  const result = await converter.render({ inputPath, outputPath });
  process.stdout.write(
    JSON.stringify({ ok: true, missingFonts: missingFontsFrom(result) }),
  );
} catch {
  process.stdout.write(JSON.stringify({ ok: false, error: "convert_failed" }));
  process.exit(1);
} finally {
  if (converter && typeof converter.dispose === "function") {
    try {
      await converter.dispose();
    } catch {
      // ignore
    }
  }
}
