#!/usr/bin/env node

// Moon phase calculation script — replicates the reference project's Get Moon Phase tool
// Uses circular-natal-horoscope-js to get actual Sun/Moon ecliptic longitudes,
// then determines phase from the Moon-Sun elongation angle.
//
// Usage:
//   node moon-phase.mjs --date "2026-03-12"
//
// Output: JSON with { phaseText, lunarDay }

import pkg from "circular-natal-horoscope-js";
const { Horoscope, Origin } = pkg;

const SYNODIC_MONTH = 29.53058770576;

// Phase boundaries (in lunar days, derived from elongation)
const PHASE_BOUNDARIES = {
  NEW_MOON_LOWER: 0,
  WAXING_CRESCENT: 1,
  FIRST_QUARTER: 6.382647,
  WAXING_GIBBOUS: 8.382647,
  FULL_MOON: 13.765294,
  WANING_GIBBOUS: 15.765294,
  LAST_QUARTER: 21.147941,
  WANING_CRESCENT: 23.147941,
  NEW_MOON_UPPER: 28.530588,
  NEW_MOON_UPPER_END: 29.530588,
};

// Get Sun and Moon ecliptic longitudes for a given date using the Moshier ephemeris.
// Location is irrelevant for geocentric ecliptic longitude, so we use (0, 0).
function getSunMoonPositions(date) {
  const horoscope = new Horoscope({
    origin: new Origin({
      year: date.getUTCFullYear(),
      month: date.getUTCMonth(),
      date: date.getUTCDate(),
      hour: date.getUTCHours(),
      minute: date.getUTCMinutes(),
      second: date.getUTCSeconds(),
      latitude: 0,
      longitude: 0,
    }),
  });

  const bodies = horoscope.CelestialBodies.all;
  const map = Object.fromEntries(bodies.map((b) => [b.key, b]));
  return {
    sun: map.sun.ChartPosition.Ecliptic.DecimalDegrees,
    moon: map.moon.ChartPosition.Ecliptic.DecimalDegrees,
  };
}

// Calculate lunar day from Sun-Moon elongation
function getLunarDay(date) {
  const { sun, moon } = getSunMoonPositions(date);
  const elongation = ((moon - sun) % 360 + 360) % 360;
  return (elongation / 360) * SYNODIC_MONTH;
}

// Determine moon phase from lunar day
function getLunarPhase(lunarDay) {
  const b = PHASE_BOUNDARIES;
  if (lunarDay < b.WAXING_CRESCENT) return "new_moon";
  if (lunarDay < b.FIRST_QUARTER) return "waxing_crescent_moon";
  if (lunarDay < b.WAXING_GIBBOUS) return "first_quarter_moon";
  if (lunarDay < b.FULL_MOON) return "waxing_gibbous_moon";
  if (lunarDay < b.WANING_GIBBOUS) return "full_moon";
  if (lunarDay < b.LAST_QUARTER) return "waning_gibbous_moon";
  if (lunarDay < b.WANING_CRESCENT) return "last_quarter_moon";
  if (lunarDay < b.NEW_MOON_UPPER) return "waning_crescent_moon";
  if (lunarDay < b.NEW_MOON_UPPER_END) return "new_moon";
  throw new Error(`Invalid lunar day: ${lunarDay}`);
}

// Parse CLI arguments
const args = process.argv.slice(2);
function getArg(name) {
  const idx = args.indexOf(`--${name}`);
  return idx !== -1 ? args[idx + 1] : undefined;
}

const date = getArg("date") || new Date().toISOString().substring(0, 10);
const d = new Date(date + "T00:00:00Z");
const lunarDay = getLunarDay(d);
const phaseText = getLunarPhase(lunarDay);

console.log(JSON.stringify({ phaseText, lunarDay: Math.round(lunarDay * 100) / 100 }, null, 2));
