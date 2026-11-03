/**
 * 生成 data/longitudes.json：中国大陆地级行政区中心经度（阿里云 DataV）+
 * modood/Administrative-divisions-of-China 的 cities.json 名单。
 *
 * 使用：在 zwds-cli 目录执行
 *   node scripts/build-longitudes.mjs
 *
 * 依赖：Node 18+，需联网。
 */

import fs from "fs";
import https from "https";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, "..");
const OUT = path.join(ROOT, "data", "longitudes.json");

const CITIES_URL =
  "https://raw.githubusercontent.com/modood/Administrative-divisions-of-China/master/dist/cities.json";

const SKIP_NAMES = new Set([
  "省直辖县级行政区划",
  "自治区直辖县级行政区划",
]);

/** 直辖市：跳过「市辖区」「县」，用全市 adcode */
const MUNICIPALITY = {
  11: { label: "北京市", adcode: 110000 },
  12: { label: "天津市", adcode: 120000 },
  31: { label: "上海市", adcode: 310000 },
  50: { label: "重庆市", adcode: 500000 },
};

const OVERSEAS = [
  {
    names: ["香港", "香港特别行政区"],
    longitude: 114.173355,
  },
  {
    names: ["澳门", "澳门特别行政区"],
    longitude: 113.54909,
  },
  { names: ["台北", "台北市"], longitude: 121.5654267 },
  { names: ["纽约", "纽约市", "New York"], longitude: -74.006 },
  { names: ["洛杉矶", "Los Angeles"], longitude: -118.2437 },
  { names: ["伦敦", "London"], longitude: -0.1278 },
  { names: ["东京", "東京都", "Tokyo"], longitude: 139.6917 },
  { names: ["新加坡", "Singapore"], longitude: 103.8198 },
  { names: ["悉尼", "Sydney"], longitude: 151.2093 },
];

function getHttps(url) {
  return new Promise((resolve, reject) => {
    https
      .get(url, { timeout: 60000 }, (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          getHttps(res.headers.location).then(resolve).catch(reject);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode} ${url}`));
          return;
        }
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () =>
          resolve(Buffer.concat(chunks).toString("utf8"))
        );
      })
      .on("error", reject);
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * @param {number} adcode
 * @returns {Promise<number>}
 */
async function fetchLongitude(adcode) {
  const url = `https://geo.datav.aliyun.com/areas_v3/bound/${adcode}.json`;
  const text = await getHttps(url);
  const j = JSON.parse(text);
  const f = j.features?.[0];
  const center = f?.properties?.center;
  if (!center || center.length < 2) throw new Error(`no center ${adcode}`);
  return Number(center[0]);
}

/** 地名别名：便于 place 含简称时命中 */
function namesForLabel(label) {
  const names = [label];
  if (label.endsWith("市")) {
    const s = label.slice(0, -1);
    if (s.length >= 2) names.push(s);
  }
  if (label.endsWith("地区")) {
    const s = label.slice(0, -2);
    if (s.length >= 2) names.push(s);
  }
  if (label.endsWith("盟")) {
    const s = label.slice(0, -1);
    if (s.length >= 2) names.push(s);
  }
  return [...new Set(names)];
}

function resolveTarget(c) {
  const p = c.provinceCode;
  const name = c.name;
  if (SKIP_NAMES.has(name)) return null;
  const m = MUNICIPALITY[Number(p)];
  if (m && (name === "市辖区" || name === "县")) {
    return { adcode: m.adcode, label: m.label };
  }
  if (name === "市辖区" || name === "县") return null;
  const adcode = parseInt(c.code, 10) * 100;
  if (!Number.isFinite(adcode) || adcode < 110000) return null;
  return { adcode, label: name };
}

async function main() {
  console.log("Fetching cities.json …");
  const cities = JSON.parse(await getHttps(CITIES_URL));

  /** @type {Map<number, string>} */
  const byAdcode = new Map();

  for (const c of cities) {
    const t = resolveTarget(c);
    if (!t) continue;
    const prev = byAdcode.get(t.adcode);
    if (!prev) byAdcode.set(t.adcode, t.label);
    else if (t.label.length < prev.length) byAdcode.set(t.adcode, t.label);
  }

  const rows = [];
  for (const [adcode, label] of byAdcode) {
    rows.push({ adcode, names: namesForLabel(label), label });
  }
  rows.sort((a, b) => a.adcode - b.adcode);

  console.log(`Unique adcodes: ${rows.length}. Fetching centers (DataV) …`);

  const entries = [];
  let fail = 0;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    try {
      const lon = await fetchLongitude(r.adcode);
      entries.push({
        names: r.names,
        longitude: Math.round(lon * 1e6) / 1e6,
      });
      if ((i + 1) % 50 === 0) console.log(`  ${i + 1}/${rows.length}`);
    } catch (e) {
      console.warn(`  skip adcode ${r.adcode} ${r.label}: ${e.message}`);
      fail++;
    }
    await sleep(60);
  }

  for (const o of OVERSEAS) entries.push(o);

  const payload = {
    _meta: {
      generated: new Date().toISOString(),
      source:
        "modood/Administrative-divisions-of-China cities.json + geo.datav.aliyun.com areas_v3/bound/{adcode}.json (center[0] as longitude)",
      entries: entries.length,
      fetch_failures: fail,
    },
    entries,
  };

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf8");
  console.log(`Wrote ${OUT} (${entries.length} entries, ${fail} fetch failures)`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
