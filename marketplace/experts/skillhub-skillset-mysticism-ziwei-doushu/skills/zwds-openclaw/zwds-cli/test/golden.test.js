const { test } = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("path");
const { calculateZwds } = require("../src/iztroClient");
const { calculateTrueSolarTime } = require("../src/solarTime");
const { hourToTimeIndex } = require("../src/timeIndex");
const { resolveLongitude } = require("../src/longitudeLookup");

test("hourToTimeIndex matches zwds-cli convention", () => {
  assert.equal(hourToTimeIndex(0), 0);
  assert.equal(hourToTimeIndex(23), 0);
  assert.equal(hourToTimeIndex(6), 3);
  assert.equal(hourToTimeIndex(2), 1);
  assert.equal(hourToTimeIndex(22), 11);
});

test("calculateTrueSolarTime: China DST 1988 subtracts 1h at lon 120", () => {
  const r = calculateTrueSolarTime("1988-08-01", "12:00", 120);
  assert.equal(r.hour, 11);
  assert.equal(r.minute, 0);
});

test("resolveLongitude: explicit longitude wins", () => {
  const r = resolveLongitude("北京市", 118);
  assert.equal(r.longitude, 118);
  assert.equal(r.source, "input");
});

test("resolveLongitude: 广州 in database", () => {
  const r = resolveLongitude("广州市", null);
  assert.equal(r.source, "database");
  assert.ok(Math.abs(r.longitude - 113.28) < 0.05);
});

test("calculateZwds: 12 palaces and 命宫", () => {
  const { data } = calculateZwds({
    birth_time: "2000-08-16T06:00:00",
    gender: "female",
  });
  assert.equal(data.palaces.length, 12);
  assert.equal(data.soul_palace.name, "命宫");
  assert.ok(typeof data.soul_palace.index === "number");
  for (const p of data.palaces) {
    assert.ok(Array.isArray(p.yearly));
  }
});

test("calculateZwds: yearly uses lichun anchor and yearly.index", () => {
  const { data } = calculateZwds({
    birth_time: "1989-09-05T10:00:00",
    gender: "male",
  });
  const fude = data.palaces.find((p) => p.name === "福德");
  const fumu = data.palaces.find((p) => p.name === "父母");
  assert.ok(fude);
  assert.ok(fumu);
  assert.ok(fumu.yearly.includes(36), "2025 age 36（立春当日口径）应在父母宫");
  assert.ok(fude.yearly.includes(37), "2026 age 37（立春当日口径）应在午宫(福德)");
  assert.ok(!fumu.yearly.includes(37), "父母宫不应误记 2026 流年命宫");
});

test("calculateZwds: birth_place enables true_solar_time object", () => {
  const { data } = calculateZwds({
    birth_time: "2000-08-16T06:00:00",
    gender: "female",
    birth_place: "上海市",
  });
  assert.ok(data.birth_info.true_solar_time);
  assert.equal(data.birth_info.true_solar_time.is_applied, true);
});

test("CLI: stdin JSON stdout success", () => {
  const cliDir = path.join(__dirname, "..");
  const payload = JSON.stringify({
    birth_time: "2000-08-16T06:00:00",
    gender: "female",
  });
  const r = spawnSync(process.execPath, ["src/index.js"], {
    cwd: cliDir,
    input: payload,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
  });
  assert.equal(r.status, 0, r.stderr);
  const j = JSON.parse(r.stdout.trim());
  assert.equal(j.success, true);
  assert.ok(j.data.palaces);
});
