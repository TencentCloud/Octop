"use strict";

function palaceByName(chart, name) {
  if (!chart || !Array.isArray(chart.palaces)) return null;
  return chart.palaces.find((p) => p.name === name) || null;
}

function getMajorStarNames(palace, limit = 2) {
  if (!palace || !Array.isArray(palace.major_stars)) return [];
  return palace.major_stars
    .filter((s) => s && s.type === "major" && s.name)
    .map((s) => s.name)
    .slice(0, limit);
}

/** 夫妻等宫无主星时，用辅星/煞曜/杂曜作弱回退（仍须来自 JSON） */
function getPalaceStarNamesFallback(palace, limit = 2) {
  const majors = getMajorStarNames(palace, limit);
  if (majors.length) return majors;
  if (!palace) return [];
  const minor = (palace.minor_stars || [])
    .filter((s) => s && s.name)
    .map((s) => s.name)
    .slice(0, limit);
  if (minor.length) return minor;
  return (palace.adjective_stars || [])
    .filter((s) => s && s.name)
    .map((s) => s.name)
    .slice(0, limit);
}

/** 本宫索引 i 的三方四正：本宫、对宫、财帛位、官禄位（与 zwds 技能约定一致） */
function sanFangIndices(i) {
  const idx = Number(i);
  if (!Number.isInteger(idx) || idx < 0 || idx > 11) return [];
  return [idx, (idx + 6) % 12, (idx + 4) % 12, (idx + 8) % 12];
}

function validateChart(chart) {
  if (!chart || typeof chart !== "object") return "chart missing";
  if (!Array.isArray(chart.palaces) || chart.palaces.length !== 12) return "palaces must be array of length 12";
  return null;
}

module.exports = {
  palaceByName,
  getMajorStarNames,
  getPalaceStarNamesFallback,
  sanFangIndices,
  validateChart,
};
