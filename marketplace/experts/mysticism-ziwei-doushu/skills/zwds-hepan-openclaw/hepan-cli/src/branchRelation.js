"use strict";

const SANHE_GROUPS = [
  ["申", "子", "辰"],
  ["亥", "卯", "未"],
  ["寅", "午", "戌"],
  ["巳", "酉", "丑"],
];

const LIUHE_PAIRS = [
  ["子", "丑"],
  ["寅", "亥"],
  ["卯", "戌"],
  ["辰", "酉"],
  ["巳", "申"],
  ["午", "未"],
];

const CHONG_PAIRS = [
  ["子", "午"],
  ["丑", "未"],
  ["寅", "申"],
  ["卯", "酉"],
  ["辰", "戌"],
  ["巳", "亥"],
];

function branchRelation(a, b) {
  if (!a || !b) return "neutral";
  if (a === b) return "same";
  for (const [x, y] of CHONG_PAIRS) {
    if ((a === x && b === y) || (a === y && b === x)) return "chong";
  }
  for (const [x, y] of LIUHE_PAIRS) {
    if ((a === x && b === y) || (a === y && b === x)) return "liuhe";
  }
  for (const g of SANHE_GROUPS) {
    if (g.includes(a) && g.includes(b) && a !== b) return "sanhe";
  }
  return "neutral";
}

module.exports = { branchRelation };
