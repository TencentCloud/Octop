import fs from "node:fs";

function read(path) {
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function keys(obj, prefix = "") {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) out.push(...keys(v, path));
    else out.push(path);
  }
  return out;
}

function compare(name, a, b) {
  const A = new Set(keys(a));
  const B = new Set(keys(b));
  const onlyEn = [...A].filter((k) => !B.has(k)).sort();
  const onlyZh = [...B].filter((k) => !A.has(k)).sort();
  console.log(
    `[${name}] en=${A.size} zh=${B.size} onlyInEn=${onlyEn.length} onlyInZh=${onlyZh.length}`,
  );
  if (onlyEn.length) console.log("  onlyInEn:", onlyEn.slice(0, 30).join(", "));
  if (onlyZh.length) console.log("  onlyInZh:", onlyZh.slice(0, 30).join(", "));
}

const en = read(process.argv[2]);
const zh = read(process.argv[3]);
const label = process.argv[4] ?? "";
compare(`${label}whole-file`, en, zh);
compare(`${label}projects`, { projects: en.projects }, { projects: zh.projects });
compare(`${label}nav`, { nav: en.nav }, { nav: zh.nav });

// Duplicate-key detection inside the "projects" block (JSON.parse hides dupes).
for (const [tag, path] of [
  ["en", process.argv[2]],
  ["zh", process.argv[3]],
]) {
  const raw = fs.readFileSync(path, "utf8");
  const start = raw.indexOf('"projects": {');
  if (start < 0) {
    console.log(`[${tag}] no projects block`);
    continue;
  }
  const end = raw.indexOf("\n  }", start);
  const block = raw.slice(start, end);
  const seen = new Map();
  for (const m of block.matchAll(/^\s{4}"([^"]+)":/gm)) {
    seen.set(m[1], (seen.get(m[1]) ?? 0) + 1);
  }
  const dupes = [...seen.entries()].filter(([, n]) => n > 1);
  console.log(
    `[${tag}] projects top-level keys=${seen.size} duplicates=${
      dupes.length ? JSON.stringify(dupes) : "none"
    }`,
  );
}
