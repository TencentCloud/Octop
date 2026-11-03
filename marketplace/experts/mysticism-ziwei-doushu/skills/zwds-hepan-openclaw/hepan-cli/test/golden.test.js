"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("node:child_process");
const { computeCompat } = require("../src/engine/computeCompat");

const root = path.join(__dirname, "..");
const zwdsFixture = path.join(__dirname, "..", "..", "..", "zwds", "fixtures", "sample-ningbo-1993-05-03-male.json");
const chartBPath = path.join(__dirname, "fixtures", "chart-b-1988.json");

function loadJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

test("computeCompat: structure and score range for sample pair", () => {
  const full = loadJson(zwdsFixture);
  assert.equal(full.success, true);
  const chartA = full.data;
  const chartB = loadJson(chartBPath);

  const out = computeCompat(chartA, chartB, {
    meta_a: full.meta,
    meta_b: { longitude_resolution: { source: "input" }, warnings: [] },
    reference_year: 2026,
  });

  assert.ok(typeof out.score === "number");
  assert.ok(out.score >= 0 && out.score <= 100);
  assert.ok(out.confidence > 0 && out.confidence <= 1);
  assert.equal(out.rule_version, "compat/v1");
  assert.ok(Array.isArray(out.dimensions));
  assert.equal(out.dimensions.length, 4);
  const lr = out.dimensions.find((d) => d.id === "life_rhythm");
  assert.ok(lr);
  assert.equal(lr.max, 12);
  assert.ok(lr.score >= 0 && lr.score <= 12);
  const capSum = out.dimensions.reduce((s, d) => s + d.max, 0);
  assert.equal(capSum, 100, "dimension_caps must sum to 100");
  for (const d of out.dimensions) {
    assert.ok(d.id);
    assert.ok(typeof d.score === "number");
    assert.ok(typeof d.max === "number");
    assert.ok(Array.isArray(d.hits));
    assert.ok(d.reason_summary && typeof d.reason_summary.display_text === "string");
    assert.ok(Array.isArray(d.reason_summary.positive_reasons));
    assert.ok(Array.isArray(d.reason_summary.negative_reasons));
  }
  assert.ok(Array.isArray(out.hits));
  assert.ok(out.hits.length > 0);
  for (const h of out.hits) {
    assert.ok(h.rule_id);
    assert.ok(h.dimension);
    assert.ok("effect" in h);
    assert.ok(h.evidence && typeof h.evidence === "object");
  }
  assert.ok(out.score >= 35 && out.score <= 96, `score ${out.score} in expected band`);
});

test("computeCompat: identical charts score in upper band", () => {
  const full = loadJson(zwdsFixture);
  const out = computeCompat(full.data, full.data, { reference_year: 2026 });
  assert.ok(out.score >= 44 && out.score <= 98, `self-pair score ${out.score}`);
});

test("CLI: stdin JSON stdout success", () => {
  const full = loadJson(zwdsFixture);
  const chartB = loadJson(chartBPath);
  const payload = JSON.stringify({
    rule_version: "compat/v1",
    chart_a: full.data,
    chart_b: chartB,
    meta_a: full.meta,
    meta_b: { longitude_resolution: { source: "default" }, warnings: ["x"] },
    reference_year: 2026,
  });
  const r = spawnSync(process.execPath, ["src/index.js"], {
    cwd: root,
    input: payload,
    encoding: "utf8",
  });
  assert.equal(r.stderr, "");
  const j = JSON.parse(r.stdout.trim());
  assert.equal(j.success, true);
  assert.ok(j.data.score >= 0 && j.data.score <= 100);
  assert.ok(j.data.confidence < 1);
  assert.equal(j.meta.engine, "hepan-cli");
});

test("CLI: invalid chart_a errors to stderr JSON", () => {
  const payload = JSON.stringify({ chart_a: { palaces: [] }, chart_b: loadJson(chartBPath) });
  const r = spawnSync(process.execPath, ["src/index.js"], {
    cwd: root,
    input: payload,
    encoding: "utf8",
  });
  assert.notEqual(r.status, 0);
  const err = JSON.parse(r.stderr.trim());
  assert.equal(err.success, false);
  assert.ok(String(err.error).includes("chart_a"));
});
