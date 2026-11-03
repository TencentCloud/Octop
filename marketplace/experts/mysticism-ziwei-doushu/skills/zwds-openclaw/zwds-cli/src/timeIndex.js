/**
 * 由真太阳时的小时映射 iztro 所需 time_index（23、0 点 → 早子 0）
 */

/**
 * @param {number} hour 0-23
 * @returns {number} time_index 0-11（与 py-iztro by_solar 一致）
 */
function hourToTimeIndex(hour) {
  if (hour === 23 || hour === 0) return 0;
  if (hour >= 1 && hour < 3) return 1;
  if (hour >= 3 && hour < 5) return 2;
  if (hour >= 5 && hour < 7) return 3;
  if (hour >= 7 && hour < 9) return 4;
  if (hour >= 9 && hour < 11) return 5;
  if (hour >= 11 && hour < 13) return 6;
  if (hour >= 13 && hour < 15) return 7;
  if (hour >= 15 && hour < 17) return 8;
  if (hour >= 17 && hour < 19) return 9;
  if (hour >= 19 && hour < 21) return 10;
  if (hour >= 21 && hour < 23) return 11;
  return 0;
}

module.exports = { hourToTimeIndex };
