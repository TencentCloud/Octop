#!/usr/bin/env node
"use strict";

const { computeCompat } = require("./engine/computeCompat");

async function readStdin() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  return Buffer.concat(chunks);
}

function decodeStdinBuffer(buf) {
  const hasUtf16LeBom = buf.length >= 2 && buf[0] === 0xff && buf[1] === 0xfe;
  const hasUtf8Bom = buf.length >= 3 && buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf;

  const zeroByteRate = (() => {
    if (!buf.length) return 0;
    let zeros = 0;
    for (const b of buf) {
      if (b === 0) zeros += 1;
    }
    return zeros / buf.length;
  })();

  // 兼容 Windows PowerShell 通过管道传 UTF-16LE JSON 的情况。
  if (hasUtf16LeBom || zeroByteRate > 0.2) {
    return buf.toString("utf16le").replace(/^\uFEFF/, "");
  }
  if (hasUtf8Bom) {
    return buf.toString("utf8").replace(/^\uFEFF/, "");
  }
  return buf.toString("utf8");
}

function main() {
  readStdin()
    .then((buf) => {
      const raw = decodeStdinBuffer(buf);
      const trimmed = raw.trim();
      if (!trimmed) {
        console.error(JSON.stringify({ success: false, error: "empty stdin; provide JSON payload" }));
        process.exit(1);
        return;
      }
      let payload;
      try {
        payload = JSON.parse(trimmed);
      } catch (e) {
        console.error(JSON.stringify({ success: false, error: `invalid JSON: ${e.message}` }));
        process.exit(1);
        return;
      }

      if (!payload.chart_a || typeof payload.chart_a !== "object") {
        console.error(JSON.stringify({ success: false, error: "missing required field: chart_a (zwds-cli data)" }));
        process.exit(1);
        return;
      }
      if (!payload.chart_b || typeof payload.chart_b !== "object") {
        console.error(JSON.stringify({ success: false, error: "missing required field: chart_b (zwds-cli data)" }));
        process.exit(1);
        return;
      }

      const ruleVersion = payload.rule_version || "compat/v1";

      try {
        const data = computeCompat(payload.chart_a, payload.chart_b, {
          rule_version: ruleVersion,
          meta_a: payload.meta_a,
          meta_b: payload.meta_b,
          reference_year: payload.reference_year,
          reference_age_a: payload.reference_age_a,
          reference_age_b: payload.reference_age_b,
        });
        console.log(
          JSON.stringify({
            success: true,
            data,
            meta: { engine: "hepan-cli", engine_version: "1.0.0" },
          })
        );
      } catch (e) {
        console.error(
          JSON.stringify({
            success: false,
            error: e.message || String(e),
          })
        );
        process.exit(1);
      }
    })
    .catch((e) => {
      console.error(JSON.stringify({ success: false, error: e.message || String(e) }));
      process.exit(1);
    });
}

main();
