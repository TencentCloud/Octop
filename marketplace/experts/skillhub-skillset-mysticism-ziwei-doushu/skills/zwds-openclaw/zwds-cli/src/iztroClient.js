const { astro } = require("iztro");
const { calculateTrueSolarTime } = require("./solarTime");
const { hourToTimeIndex } = require("./timeIndex");
const { resolveLongitude } = require("./longitudeLookup");

/**
 * 从 ISO 字符串截取字面年月日时分（不按时区重算钟表时间）
 */
function parseBirthComponents(iso) {
  const m = String(iso)
    .trim()
    .match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (!m) throw new Error("invalid birth_time: expected ISO like 2000-08-16T06:00:00");
  return {
    year: +m[1],
    month: +m[2],
    day: +m[3],
    hour: +m[4],
    minute: +m[5],
  };
}

function normMutagen(m) {
  if (m == null || m === "") return null;
  return m;
}

function mapStar(s) {
  return {
    name: s.name,
    type: s.type,
    brightness: s.brightness || null,
    mutagen: normMutagen(s.mutagen),
  };
}

function buildPalaces(chart) {
  return chart.palaces.map((palace) => ({
    index: palace.index,
    name: palace.name,
    is_body_palace: palace.isBodyPalace,
    is_original_palace: palace.isOriginalPalace,
    heavenly_stem: palace.heavenlyStem,
    earthly_branch: palace.earthlyBranch,
    major_stars: palace.majorStars.map(mapStar),
    minor_stars: palace.minorStars.map(mapStar),
    adjective_stars: palace.adjectiveStars.map(mapStar),
    changsheng12: palace.changsheng12,
    boshi12: palace.boshi12,
    jiangqian12: palace.jiangqian12,
    suiqian12: palace.suiqian12,
    decadal: {
      range: palace.decadal.range,
      heavenly_stem: palace.decadal.heavenlyStem,
      earthly_branch: palace.decadal.earthlyBranch,
    },
    ages: palace.ages,
  }));
}

/**
 * 各宫 `yearly`：列出 age = 阳历年 Y − 出生公历年 时，该本命宫作为流年命宫的年份。
 * iztro 的 `horoscope(Y-M-D).yearly.palaceNames` 按流年盘旋转排列，**不能**与本命
 * `palaces` 的下标一一对应；应使用 `horoscope(...).yearly.index`（本命宫位下标）。
 * 锚点用 `Y-02-04`（立春当日口径）：用于统一流年换年判断。
 * 说明：当前实现按日期锚点，不细分立春具体交接时刻。
 */
function computeYearlyAges(chart, birthYear, palacesForYearly) {
  const yearlyAgesByPalace = {};
  for (const p of palacesForYearly) {
    yearlyAgesByPalace[p.index] = [];
  }

  const startYear = birthYear;
  const endYear = birthYear + 120;

  for (let year = startYear; year <= endYear; year++) {
    if (year < 1900 || year > 2100) continue;
    try {
      const horoscope = chart.horoscope(`${year}-2-4`);
      const idx = horoscope.yearly?.index;
      if (typeof idx !== "number" || idx < 0) continue;
      const age = year - birthYear;
      if (age >= 0 && yearlyAgesByPalace[idx] != null) {
        yearlyAgesByPalace[idx].push(age);
      }
    } catch {
      /* 单年 horoscope 失败则跳过，继续下一年 */
    }
  }

  for (const p of palacesForYearly) {
    yearlyAgesByPalace[p.index].sort((a, b) => a - b);
  }
  return yearlyAgesByPalace;
}

/**
 * @param {object} input
 * @param {string} input.birth_time ISO
 * @param {string} [input.birth_place]
 * @param {string} [input.gender] male|female
 * @param {number} [input.longitude]
 * @param {string} [input.language] default zh-CN
 */
function calculateZwds(input) {
  const {
    birth_time,
    birth_place = null,
    gender = null,
    longitude: inputLongitude = null,
    language = "zh-CN",
  } = input;

  const bc = parseBirthComponents(birth_time);
  const genderCn = gender === "female" ? "女" : "男";

  let trueSolarHour = bc.hour;
  let trueSolarMinute = bc.minute;
  let usedLongitude = 120.0;
  let isTrueSolarTime = false;
  /** @type {string[]} */
  const warnings = [];

  const lonRes = resolveLongitude(birth_place, inputLongitude);
  usedLongitude = lonRes.longitude;
  if (lonRes.warning === "place_not_in_database") {
    warnings.push(
      "birth_place not found in longitudes.json; using default longitude 120.0 for solar time"
    );
  }
  if (lonRes.warning === "empty_place") {
    warnings.push("no birth_place; using default longitude 120.0 (no true-solar correction by location)");
  }

  if (birth_place && String(birth_place).trim()) {
    try {
      usedLongitude = lonRes.longitude;
      const birthDateStr = `${bc.year}-${String(bc.month).padStart(2, "0")}-${String(bc.day).padStart(2, "0")}`;
      const birthTimeStr = `${String(bc.hour).padStart(2, "0")}:${String(bc.minute).padStart(2, "0")}`;
      const tst = calculateTrueSolarTime(birthDateStr, birthTimeStr, usedLongitude);
      trueSolarHour = tst.hour;
      trueSolarMinute = tst.minute;
      usedLongitude = tst.longitude;
      isTrueSolarTime = true;
    } catch {
      trueSolarHour = bc.hour;
      trueSolarMinute = bc.minute;
      warnings.push("true solar time calculation failed; using original clock time");
    }
  }

  const timeIndex = hourToTimeIndex(trueSolarHour);
  const solarDateStr = `${bc.year}-${bc.month}-${bc.day}`;

  const chart = astro.bySolar(solarDateStr, timeIndex, genderCn, true, language);

  const palaces = buildPalaces(chart);
  const yearlyAgesByPalace = computeYearlyAges(chart, bc.year, palaces);
  for (const p of palaces) {
    p.yearly = yearlyAgesByPalace[p.index] || [];
  }

  let soulPalaceIndex = null;
  for (const p of palaces) {
    if (p.name === "命宫" && soulPalaceIndex === null) {
      soulPalaceIndex = p.index;
      break;
    }
  }

  const result = {
    birth_info: {
      solar_date: chart.solarDate,
      lunar_date: chart.lunarDate,
      chinese_date: chart.chineseDate,
      time: chart.time,
      time_range: chart.timeRange,
      sign: chart.sign,
      zodiac: chart.zodiac,
      gender: chart.gender,
      birth_place,
      true_solar_time: isTrueSolarTime
        ? {
            is_applied: true,
            hour: trueSolarHour,
            minute: trueSolarMinute,
            longitude: usedLongitude,
            original_time: `${String(bc.hour).padStart(2, "0")}:${String(bc.minute).padStart(2, "0")}`,
            true_solar_time_str: `${String(trueSolarHour).padStart(2, "0")}:${String(trueSolarMinute).padStart(2, "0")}`,
          }
        : null,
    },
    soul_palace: {
      earthly_branch: chart.earthlyBranchOfSoulPalace,
      soul: chart.soul,
    },
    body_palace: {
      earthly_branch: chart.earthlyBranchOfBodyPalace,
      body: chart.body,
    },
    five_elements_class: chart.fiveElementsClass,
    palaces,
  };

  if (soulPalaceIndex != null) {
    result.soul_palace.index = soulPalaceIndex;
    result.soul_palace.name = "命宫";
  }

  return {
    data: result,
    meta: {
      iztro_version: "2.5.0",
      time_index: timeIndex,
      longitude_resolution: lonRes,
      warnings,
    },
  };
}

module.exports = { calculateZwds, parseBirthComponents };
