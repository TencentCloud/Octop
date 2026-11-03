#!/usr/bin/env node
/**
 * 紫微斗数排盘计算脚本
 * 使用 iztro 库进行排盘计算
 * 支持真太阳时校正、闰月（按下月）、子时（按次日）规则
 */

const { astro } = require('iztro');

/**
 * 时辰映射：小时 → iztro 时辰索引
 * iztro 索引：0=早子(23-1), 1=丑(1-3), 2=寅(3-5), 3=卯(5-7),
 *            4=辰(7-9), 5=巳(9-11), 6=午(11-13), 7=未(13-15),
 *            8=申(15-17), 9=酉(17-19), 10=戌(19-21), 11=亥(21-23), 12=晚子(23-24)
 */
function hourToShichenIndex(hour) {
  if (hour >= 23 || hour < 1) return 0;  // 子时
  if (hour >= 1 && hour < 3) return 1;   // 丑时
  if (hour >= 3 && hour < 5) return 2;   // 寅时
  if (hour >= 5 && hour < 7) return 3;   // 卯时
  if (hour >= 7 && hour < 9) return 4;   // 辰时
  if (hour >= 9 && hour < 11) return 5;  // 巳时
  if (hour >= 11 && hour < 13) return 6; // 午时
  if (hour >= 13 && hour < 15) return 7; // 未时
  if (hour >= 15 && hour < 17) return 8; // 申时
  if (hour >= 17 && hour < 19) return 9; // 酉时
  if (hour >= 19 && hour < 21) return 10;// 戌时
  if (hour >= 21 && hour < 23) return 11;// 亥时
  return 0;
}

/**
 * 处理子时规则：23:00-24:00 视为次日早子时
 */
function handleZiHour(birthDate, birthTime) {
  const [hours] = birthTime.split(':').map(Number);
  
  if (hours >= 23) {
    const date = new Date(birthDate);
    date.setDate(date.getDate() + 1);
    const nextDate = date.toISOString().split('T')[0];
    return { date: nextDate, isZiHour: true, originalDate: birthDate };
  }
  
  return { date: birthDate, isZiHour: false, originalDate: birthDate };
}

/**
 * 处理闰月规则：闰月视为下月
 * @param {string} lunarDate - 农历日期 YYYY-M-D
 * @param {number} month - 原始月份
 * @returns {object} 调整后的月份和日期
 */
function handleLeapMonth(lunarDate, month) {
  const newMonth = month + 1;
  const parts = lunarDate.split('-');
  let year = parseInt(parts[0]);
  let day = parts[2] || parts[1]; // 兼容不同格式
  
  if (newMonth > 12) {
    return { lunarDate: `${year + 1}-1-${day}`, month: 1, note: `闰${month}月按次年正月算` };
  }
  return { lunarDate: `${year}-${newMonth}-${day}`, month: newMonth, note: `闰${month}月按${newMonth}月算` };
}

/**
 * 真太阳时校正（简化版）
 * 返回校正分钟数
 */
function correctSolarTime(location) {
  const longitudes = {
    '北京': 116.4, '天津': 117.2, '上海': 121.5, '重庆': 106.6,
    '山西': 112.6, '太原': 112.6, '榆次': 112.7,
    '河北': 114.5, '内蒙古': 111.7, '辽宁': 123.4, '沈阳': 123.4,
    '吉林': 125.3, '长春': 125.3, '黑龙江': 126.6, '哈尔滨': 126.6,
    '江苏': 118.8, '南京': 118.8, '浙江': 120.2, '杭州': 120.2,
    '安徽': 117.3, '合肥': 117.3, '福建': 119.3, '福州': 119.3,
    '江西': 115.9, '南昌': 115.9, '山东': 117.0, '济南': 117.0,
    '河南': 113.6, '郑州': 113.6, '湖北': 114.3, '武汉': 114.3,
    '湖南': 113.0, '长沙': 113.0, '广东': 113.3, '广州': 113.3,
    '深圳': 114.1, '广西': 108.3, '南宁': 108.3,
    '海南': 110.3, '海口': 110.3, '四川': 104.1, '成都': 104.1,
    '贵州': 106.7, '贵阳': 106.7, '云南': 102.7, '昆明': 102.7,
    '西藏': 91.1, '拉萨': 91.1, '陕西': 108.9, '西安': 108.9,
    '甘肃': 103.8, '兰州': 103.8, '青海': 101.8, '西宁': 101.8,
    '宁夏': 106.2, '银川': 106.2, '新疆': 87.6, '乌鲁木齐': 87.6
  };
  
  for (const [city, lon] of Object.entries(longitudes)) {
    if (location.includes(city)) {
      return Math.round((120 - lon) * 4); // 分钟
    }
  }
  return 0;
}

/**
 * 应用真太阳时校正后判断是否跨时辰
 */
function applyTimeCorrection(birthTime, correctionMinutes) {
  const [hours, minutes] = birthTime.split(':').map(Number);
  const totalMinutes = hours * 60 + minutes + correctionMinutes;
  const correctedHour = Math.floor(totalMinutes / 60) % 24;
  const correctedMin = totalMinutes % 60;
  return {
    correctedTime: `${String(correctedHour).padStart(2, '0')}:${String(Math.round(correctedMin)).padStart(2, '0')}`,
    correctedHour
  };
}

/**
 * 排盘主函数
 * @param {object} options
 * @param {string} options.birthDate - YYYY-MM-DD（阳历）或 YYYY-M-D（农历）
 * @param {string} options.birthTime - HH:MM
 * @param {string} options.gender - '男' 或 '女'
 * @param {string} options.location - 出生地点
 * @param {boolean} options.lunar - 是否农历输入
 * @param {boolean} options.isLeapMonth - 是否闰月
 */
function calculateChart(options) {
  const { birthDate, birthTime, gender, location, lunar = false, isLeapMonth = false } = options;
  
  // 1. 真太阳时校正
  const correctionMinutes = correctSolarTime(location || '');
  const { correctedTime, correctedHour } = applyTimeCorrection(birthTime, correctionMinutes);
  
  // 2. 处理子时（校正后的时间）
  const ziHourAdj = handleZiHour(birthDate, correctedTime);
  let useDate = ziHourAdj.date;
  
  // 3. 时辰索引（关键！iztro 需要索引不是小时数）
  const shichenIndex = hourToShichenIndex(correctedHour);
  
  // 4. 处理闰月（闰月视为下月）
  let leapMonthNote = null;
  let finalDate = useDate;
  if (lunar && isLeapMonth) {
    const parts = birthDate.split('-');
    const month = parseInt(parts[1]);
    const adj = handleLeapMonth(birthDate, month);
    finalDate = adj.lunarDate;
    leapMonthNote = adj.note;
  }
  
  // 5. 使用 iztro 排盘
  let a;
  if (lunar) {
    a = astro.byLunar(finalDate, shichenIndex, gender, false, true, 'zh-CN');
  } else {
    a = astro.bySolar(useDate, shichenIndex, gender, true, 'zh-CN');
  }
  
  // 6. 宫位名称（iztro 用"仆役"不是"交友"）
  const palaceNames = ['命宫','兄弟','夫妻','子女','财帛','疾厄','迁移','仆役','官禄','田宅','福德','父母'];
  
  // 7. 提取宫位数据
  const palaces = palaceNames.map(name => {
    try {
      const p = a.palace(name);
      return {
        name,
        index: p.index,
        position: p.earthlyBranch,
        heavenlyStem: p.heavenlyStem,
        majorStars: p.majorStars?.map(s => ({ name: s.name, brightness: s.brightness, mutagen: s.mutagen })) || [],
        minorStars: p.minorStars?.map(s => ({ name: s.name, brightness: s.brightness })) || [],
        adjectiveStars: p.adjectiveStars?.map(s => ({ name: s.name })) || [],
        isEmpty: !p.majorStars || p.majorStars.length === 0,
        decadal: p.decadal
      };
    } catch(e) {
      return { name, index: -1, position: '?', heavenlyStem: '?', majorStars: [], minorStars: [], adjectiveStars: [], isEmpty: true };
    }
  });
  
  // 8. 来因宫（年干所在宫位）
  const yearStem = a.chineseDate?.split(' ')[0]?.charAt(0) || '';
  const causePalace = palaces.find(p => p.heavenlyStem === yearStem);
  
  // 9. 大限
  const decades = palaces.filter(p => p.decadal?.range).map(p => ({
    palace: p.name,
    startAge: p.decadal.range[0],
    endAge: p.decadal.range[1],
    heavenlyStem: p.decadal.heavenlyStem,
    earthlyBranch: p.decadal.earthlyBranch
  })).sort((a, b) => a.startAge - b.startAge);
  
  return {
    basic: {
      solarDate: birthDate,
      lunarDate: a.lunarDate,
      chineseDate: a.chineseDate,
      time: birthTime,
      correctedTime,
      timeCorrection: correctionMinutes,
      shichenIndex,
      shichen: a.time,
      gender,
      location,
      zodiac: a.zodiac,
      constellation: a.sign,
      fiveElements: a.fiveElementsClass,
      isZiHour: ziHourAdj.isZiHour,
      isLeapMonth,
      leapMonthNote
    },
    fourPillars: {
      year: a.chineseDate?.split(' ')[0] || '',
      month: a.chineseDate?.split(' ')[1] || '',
      day: a.chineseDate?.split(' ')[2] || '',
      hour: a.chineseDate?.split(' ')[3] || ''
    },
    palaces,
    causePalace,
    yearStem,
    decades,
    lifePalace: palaces.find(p => p.name === '命宫'),
    bodyPalace: null
  };
}

// CLI 入口
if (require.main === module) {
  const args = process.argv.slice(2);
  const options = {};
  
  args.forEach(arg => {
    if (arg.startsWith('--birth=')) {
      const val = arg.split('=')[1];
      const spaceIdx = val.indexOf(' ');
      if (spaceIdx > 0) {
        options.birthDate = val.substring(0, spaceIdx);
        options.birthTime = val.substring(spaceIdx + 1);
      } else {
        options.birthDate = val;
        options.birthTime = '12:00';
      }
    } else if (arg.startsWith('--location=')) {
      options.location = arg.split('=')[1];
    } else if (arg.startsWith('--gender=')) {
      options.gender = arg.split('=')[1];
    } else if (arg === '--lunar') {
      options.lunar = true;
    } else if (arg === '--leap') {
      options.isLeapMonth = true;
    }
  });
  
  if (!options.birthDate || !options.gender) {
    console.error('用法：node calculate.js --birth="YYYY-MM-DD HH:MM" --location="地点" --gender="男/女" [--lunar] [--leap]');
    console.error('  --lunar  农历输入');
    console.error('  --leap   闰月（自动按下月算）');
    process.exit(1);
  }
  
  const chart = calculateChart(options);
  console.log(JSON.stringify(chart, null, 2));
}

module.exports = { calculateChart, hourToShichenIndex, handleLeapMonth, correctSolarTime };
