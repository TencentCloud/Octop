import fs from "node:fs";

const files = [
  "D:/nancc/octop/Octop-develop/dashboard/src/pages/Projects/index.tsx",
  "D:/nancc/octop/Octop-develop/dashboard/src/pages/Projects/Detail/index.tsx",
];
const en = JSON.parse(
  fs.readFileSync(
    "D:/nancc/octop/Octop-develop/dashboard/src/locales/en.json",
    "utf8",
  ),
);
const zh = JSON.parse(
  fs.readFileSync(
    "D:/nancc/octop/Octop-develop/dashboard/src/locales/zh.json",
    "utf8",
  ),
);

function get(obj, dotted) {
  let cur = obj;
  for (const part of dotted.split(".")) {
    if (cur === null || typeof cur !== "object" || !(part in cur)) {
      return undefined;
    }
    cur = cur[part];
  }
  return cur;
}

const used = new Set();
for (const file of files) {
  const src = fs.readFileSync(file, "utf8");
  for (const m of src.matchAll(/\bt\(\s*"([^"]+)"/g)) used.add(m[1]);
  for (const m of src.matchAll(/"((?:projects|common)\.[A-Za-z0-9_]+)"/g)) {
    used.add(m[1]);
  }
}

const missingEn = [...used].filter((k) => get(en, k) === undefined).sort();
const missingZh = [...used].filter((k) => get(zh, k) === undefined).sort();
console.log(`used keys: ${used.size}`);
console.log(`missing in en: ${missingEn.length ? missingEn.join(", ") : "none"}`);
console.log(`missing in zh: ${missingZh.length ? missingZh.join(", ") : "none"}`);
console.log(
  `sanity (en.common.actions -> ${JSON.stringify(get(en, "common.actions"))}, zh.projects.title -> ${JSON.stringify(get(zh, "projects.title"))})`,
);
