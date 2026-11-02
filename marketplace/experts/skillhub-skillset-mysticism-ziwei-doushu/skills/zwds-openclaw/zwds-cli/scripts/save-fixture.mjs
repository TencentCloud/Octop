/**
 * 将「排盘入参 + CLI 完整输出」写入 zwds/fixtures/*.json，便于读盘时直接引用、无需每次重跑 CLI。
 *
 * 用法（在 zwds-cli 目录）：
 *   node scripts/save-fixture.mjs [输入.json] [输出路径] [可选标题]
 *
 * 默认：examples/sample-payload.json → ../fixtures/sample-ningbo-1993-05-03-male.json
 */

import { spawnSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const cliRoot = path.join(__dirname, "..");
const zwdsRoot = path.join(cliRoot, "..");

const inputPath =
  process.argv[2] || path.join(cliRoot, "examples", "sample-payload.json");
const outPath =
  process.argv[3] ||
  path.join(zwdsRoot, "fixtures", "sample-ningbo-1993-05-03-male.json");
const titleArg = process.argv.slice(4).join(" ").trim();

function deriveTitle(o) {
  const place = (o.birth_place || "").replace(/\s/g, "") || "无出生地";
  const g = o.gender === "female" ? "女" : "男";
  return `${place} · ${o.birth_time || "?"} · ${g}`;
}

const inputBuf = fs.readFileSync(inputPath);
const inputObj = JSON.parse(inputBuf.toString("utf8"));

const r = spawnSync(process.execPath, ["src/index.js"], {
  cwd: cliRoot,
  input: inputBuf,
  encoding: "utf8",
  maxBuffer: 32 * 1024 * 1024,
});

if (r.status !== 0) {
  console.error(r.stderr || r.stdout);
  process.exit(r.status ?? 1);
}

let body;
try {
  body = JSON.parse(r.stdout.trim());
} catch (e) {
  console.error("Invalid CLI stdout:", r.stdout.slice(0, 200));
  process.exit(1);
}

if (!body.success) {
  console.error("CLI returned success:false", body.error);
  process.exit(1);
}

let pkg = {};
try {
  pkg = JSON.parse(
    fs.readFileSync(path.join(cliRoot, "package.json"), "utf8")
  );
} catch {
  /* ignore */
}

const _fixture = {
  schema: "zwds-fixture-v1",
  title: titleArg || deriveTitle(inputObj),
  input: inputObj,
  iztro_version: body.meta?.iztro_version ?? null,
  zwds_cli: pkg.version ?? null,
  saved_at: new Date().toISOString(),
  note:
    "读盘阶段请只使用 success 与 data（及必要的 meta.warnings / longitude_resolution）。重建本文件：在 zwds-cli 下执行 node scripts/save-fixture.mjs <此 input 同源文件> <本文件路径>",
};

const wrapped = { _fixture, ...body };
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, JSON.stringify(wrapped, null, 2), "utf8");
console.log("Wrote", path.resolve(outPath));
