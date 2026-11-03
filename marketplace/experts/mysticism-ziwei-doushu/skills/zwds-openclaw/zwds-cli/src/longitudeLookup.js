const fs = require("fs");
const path = require("path");

/**
 * @typedef {{ names: string[], longitude: number }} LongitudeEntry
 */

/** @returns {LongitudeEntry[]} */
function loadLongitudeEntries() {
  const fp = path.join(__dirname, "..", "data", "longitudes.json");
  const raw = JSON.parse(fs.readFileSync(fp, "utf8"));
  if (Array.isArray(raw.entries)) return raw.entries;
  return [];
}

let _cached = null;
function getEntries() {
  if (!_cached) _cached = loadLongitudeEntries();
  return _cached;
}

/**
 * @param {string | undefined | null} birthPlace
 * @param {number | string | undefined | null} explicitLongitude
 * @returns {{ longitude: number, source: 'input'|'database'|'default', matched?: string | null, warning?: string }}
 */
function resolveLongitude(birthPlace, explicitLongitude) {
  if (explicitLongitude != null && explicitLongitude !== "") {
    const n = Number(explicitLongitude);
    if (Number.isFinite(n)) {
      return { longitude: n, source: "input", matched: null };
    }
  }

  const place = (birthPlace || "").trim();
  if (!place) {
    return {
      longitude: 120.0,
      source: "default",
      matched: null,
      warning: "empty_place",
    };
  }

  const entries = getEntries();
  const candidates = [];
  for (const e of entries) {
    for (const name of e.names || []) {
      if (!name) continue;
      candidates.push({ name, longitude: e.longitude, len: name.length });
    }
  }
  candidates.sort((a, b) => b.len - a.len);

  for (const { name, longitude } of candidates) {
    if (place === name || place.includes(name) || name.includes(place)) {
      return { longitude, source: "database", matched: name };
    }
  }

  return {
    longitude: 120.0,
    source: "default",
    matched: null,
    warning: "place_not_in_database",
  };
}

module.exports = { loadLongitudeEntries, resolveLongitude, getEntries };
