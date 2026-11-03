#!/usr/bin/env node

// Deterministic score generation — produces stable scores for the same inputs
// Used by Predict Report (per-topic scores) and Synastry Report (overall score)
//
// Usage:
//   node random-score.mjs --seed "1990-06-15:2026-03-12:career"    # returns { score }
//   node random-score.mjs --seed "1990-06-15:2026-03-12:career" --with-category  # returns { score, category }
//   node random-score.mjs                                           # fallback: random score
//
// Output: JSON with score (40–100) and optional category

import { createHash, randomInt } from "node:crypto";

const args = process.argv.slice(2);
function getArg(name) {
  const idx = args.indexOf(`--${name}`);
  return idx !== -1 ? args[idx + 1] : undefined;
}

const seed = getArg("seed");
const withCategory = args.includes("--with-category");

let score;
if (seed) {
  const hash = createHash("sha256").update(seed).digest();
  score = (hash.readUInt32BE(0) % 61) + 40; // 40–100
} else {
  score = randomInt(40, 101);
}

const result = { score };

if (withCategory) {
  result.category = score >= 65 ? "powerIn" : "pressureIn";
}

console.log(JSON.stringify(result, null, 2));
