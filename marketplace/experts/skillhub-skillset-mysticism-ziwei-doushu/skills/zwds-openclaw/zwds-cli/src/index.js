#!/usr/bin/env node
const { calculateZwds } = require("./iztroClient");

async function readStdin() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  return Buffer.concat(chunks).toString("utf8");
}

function main() {
  readStdin()
    .then((raw) => {
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
        console.error(
          JSON.stringify({ success: false, error: `invalid JSON: ${e.message}` })
        );
        process.exit(1);
        return;
      }

      if (!payload.birth_time) {
        console.error(
          JSON.stringify({ success: false, error: "missing required field: birth_time" })
        );
        process.exit(1);
        return;
      }

      try {
        const { data, meta } = calculateZwds(payload);
        console.log(JSON.stringify({ success: true, data, meta }));
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
