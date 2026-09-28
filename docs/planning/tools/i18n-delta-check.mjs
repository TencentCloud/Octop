import { execFileSync } from "node:child_process";
import fs from "node:fs";

const repo = "D:/nancc/octop/Octop-develop";

function keys(obj, prefix = "") {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) out.push(...keys(v, path));
    else out.push(path);
  }
  return out;
}

for (const locale of ["en", "zh"]) {
  const rel = `dashboard/src/locales/${locale}.json`;
  const head = JSON.parse(
    execFileSync("git", ["show", `HEAD:${rel}`], { cwd: repo, encoding: "utf8" }),
  );
  const cur = JSON.parse(fs.readFileSync(`${repo}/${rel}`, "utf8"));
  const H = new Set(keys(head));
  const C = new Set(keys(cur));
  const added = [...C].filter((k) => !H.has(k)).sort();
  const removed = [...H].filter((k) => !C.has(k)).sort();
  console.log(
    `[${locale}] keys head=${H.size} current=${C.size} added=${added.length} removed=${removed.length}`,
  );
  console.log(`  added: ${added.join(", ")}`);
  if (removed.length) console.log(`  REMOVED: ${removed.join(", ")}`);
}
