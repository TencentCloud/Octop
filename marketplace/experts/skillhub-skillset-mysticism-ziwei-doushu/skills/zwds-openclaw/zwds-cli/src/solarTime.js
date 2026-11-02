/**
 * 简化真太阳时：钟表时间 − 中国大陆夏令时（1986–1991 段内减 1 小时）+ 经度修正 (lon−120)×4 分钟
 */

function parseDateParts(birthDateStr) {
  const [y, m, d] = birthDateStr.split("-").map((x) => parseInt(x, 10));
  return { year: y, month: m, day: d };
}

function parseTimeParts(birthTimeStr) {
  const [h, mi] = birthTimeStr.split(":").map((x) => parseInt(x, 10));
  return { hour: h, minute: mi };
}

/** @type {Record<number, [Date, Date]>} */
const DST_RANGES = {
  1986: [new Date(1986, 4, 4), new Date(1986, 8, 14)],
  1987: [new Date(1987, 3, 12), new Date(1987, 8, 13)],
  1988: [new Date(1988, 3, 10), new Date(1988, 8, 11)],
  1989: [new Date(1989, 3, 16), new Date(1989, 8, 17)],
  1990: [new Date(1990, 3, 15), new Date(1990, 8, 16)],
  1991: [new Date(1991, 3, 14), new Date(1991, 8, 15)],
};

function isInChinaDst(year, month, day) {
  const range = DST_RANGES[year];
  if (!range) return false;
  const [start, end] = range;
  const bd = new Date(year, month - 1, day);
  return bd >= start && bd <= end;
}

/**
 * @param {string} birthDateStr YYYY-MM-DD
 * @param {string} birthTimeStr HH:MM
 * @param {number} longitude
 * @returns {{ hour: number, minute: number, longitude: number }}
 */
function calculateTrueSolarTime(birthDateStr, birthTimeStr, longitude) {
  try {
    const { year, month, day } = parseDateParts(birthDateStr);
    const { hour, minute } = parseTimeParts(birthTimeStr);
    let minutes = hour * 60 + minute;

    let dstCorrection = 0;
    if (isInChinaDst(year, month, day)) {
      dstCorrection = 60;
    }

    const longitudeCorrection = (longitude - 120) * 4;
    let correctedMinutes = minutes - dstCorrection + longitudeCorrection;

    while (correctedMinutes < 0) correctedMinutes += 24 * 60;
    while (correctedMinutes >= 24 * 60) correctedMinutes -= 24 * 60;

    const total = Math.round(correctedMinutes);
    return {
      hour: Math.floor(total / 60),
      minute: total % 60,
      longitude,
    };
  } catch {
    try {
      const { hour, minute } = parseTimeParts(birthTimeStr);
      return { hour, minute, longitude };
    } catch {
      return { hour: 0, minute: 0, longitude };
    }
  }
}

module.exports = { calculateTrueSolarTime, isInChinaDst };
