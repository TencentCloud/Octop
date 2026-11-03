#!/usr/bin/env node
/**
 * 北派紫微斗数解盘脚本
 */

const STAR_MEANINGS = {
  '紫微': '帝王之星，领导才能，喜掌控',
  '天机': '智慧之星，善谋略，喜变动',
  '太阳': '光明之星，热情开朗，喜表现',
  '武曲': '将星，刚毅果断，重义气',
  '天同': '福星，温和善良，喜享受',
  '廉贞': '次桃花，复杂多变，有才华',
  '天府': '库星，稳重保守，善理财',
  '太阴': '财星，温柔内敛，重感情',
  '贪狼': '桃花星，多才多艺，喜交际',
  '巨门': '暗星，善辩才，易是非',
  '天相': '印星，正直可靠，重形象',
  '天梁': '荫星，老成持重，喜助人',
  '七杀': '将星，果断刚烈，喜冲锋',
  '破军': '耗星，变动创新，喜突破'
};

const CAUSE_PALACE_MEANINGS = {
  '命宫': '一生注重自我发展，命运掌握在自己手中',
  '兄弟': '重视兄弟姐妹、朋友关系，合作中求发展',
  '夫妻': '婚姻感情是人生重点，配偶影响大',
  '子女': '子女缘深，或适合从事教育、创意行业',
  '财帛': '财运是核心关注，一生为财奔波',
  '疾厄': '健康是重点，或适合医疗、养生行业',
  '迁移': '适合外出发展，变动中求机遇',
  '仆役': '人脉是关键，朋友多助力也多是非',
  '官禄': '事业心强，工作成就决定人生高度',
  '田宅': '重视家庭、房产，不动产缘分深',
  '福德': '精神追求高，晚年运势关键',
  '父母': '家庭背景影响大，或适合公职'
};

function analyzeLifePalace(chart) {
  const life = chart.lifePalace;
  if (!life) return null;
  
  const starNames = life.majorStars.map(s => s.name);
  const personality = getPersonalityType(starNames);
  
  return {
    palace: '命宫',
    position: life.position,
    stars: starNames,
    interpretation: starNames.map(s => STAR_MEANINGS[s]).filter(Boolean).join('、'),
    personality
  };
}

function getPersonalityType(starNames) {
  if (starNames.includes('紫微')) return '领导型：有威严，喜掌控，重面子';
  if (starNames.includes('天机')) return '谋略型：善思考，喜变动，重智慧';
  if (starNames.includes('太阳')) return '外向型：热情开朗，喜表现，重名声';
  if (starNames.includes('武曲')) return '实干型：刚毅果断，重义气，执行力强';
  if (starNames.includes('天同')) return '享受型：温和善良，喜安逸，人缘好';
  if (starNames.includes('太阴')) return '内敛型：温柔细腻，重感情，财运佳';
  if (starNames.includes('贪狼')) return '交际型：多才多艺，喜社交，欲望强';
  if (starNames.includes('巨门')) return '思辨型：善分析，口才好，易是非';
  return '综合型：需结合三方四正分析';
}

function analyzeCausePalace(chart) {
  const cause = chart.causePalace;
  if (!cause) return null;
  
  return {
    palace: cause.name,
    stem: cause.heavenlyStem,
    meaning: CAUSE_PALACE_MEANINGS[cause.name] || '需结合全盘分析'
  };
}

function analyzeDecade(chart, age) {
  const current = chart.decades.find(d => age >= d.startAge && age <= d.endAge);
  if (!current) return null;
  
  const focus = {
    '命宫': '自我发展、人生方向',
    '夫妻': '婚姻感情、合作关系',
    '财帛': '财运、收入、理财',
    '官禄': '事业、工作、成就',
    '田宅': '家庭、房产、稳定',
    '迁移': '外出、变动、机遇'
  };
  
  const advice = age < 35 ? '积累期，多学习，少冲动' 
           : age < 50 ? '发展期，把握机遇，注意平衡'
           : age < 65 ? '稳定期，守成为主，注意健康'
           : '享受期，放下执念，安享晚年';
  
  return {
    ageRange: `${current.startAge}-${current.endAge}岁`,
    palace: current.palace,
    focus: focus[current.palace] || current.palace,
    advice
  };
}

function analyzeYear(year) {
  const stems = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸'];
  const stem = stems[(year - 4) % 10];
  
  const focuses = {
    '甲': '事业开拓', '乙': '合作发展', '丙': '名声地位',
    '丁': '稳定守成', '戊': '诚信立身', '己': '内敛修养',
    '庚': '变革突破', '辛': '精细打磨', '壬': '智慧谋略', '癸': '蓄势待发'
  };
  
  return {
    year,
    stem,
    focus: focuses[stem] || '平稳发展'
  };
}

function answerQuestion(chart, question) {
  const q = question.toLowerCase();
  
  if (q.includes('事业') || q.includes('工作')) {
    const guanlu = chart.palaces.find(p => p.name === '官禄');
    return {
      type: '事业',
      palace: '官禄宫',
      stars: guanlu?.majorStars.map(s => s.name) || [],
      analysis: '官禄宫代表事业发展',
      advice: '结合大限流年判断机遇期'
    };
  }
  
  if (q.includes('财') || q.includes('钱')) {
    const caibo = chart.palaces.find(p => p.name === '财帛');
    return {
      type: '财运',
      palace: '财帛宫',
      stars: caibo?.majorStars.map(s => s.name) || [],
      analysis: '财帛宫代表财运收入',
      advice: '禄存化禄财运佳，化忌需谨慎理财'
    };
  }
  
  if (q.includes('婚姻') || q.includes('感情')) {
    const fuqi = chart.palaces.find(p => p.name === '夫妻');
    return {
      type: '婚姻',
      palace: '夫妻宫',
      stars: fuqi?.majorStars.map(s => s.name) || [],
      analysis: '夫妻宫代表婚姻感情',
      advice: '空宫需借对宫，化忌需注意沟通'
    };
  }
  
  return null;
}

function generateReport(chart, question = null) {
  const birthYear = parseInt(chart.basic.solarDate.split('-')[0]);
  const age = new Date().getFullYear() - birthYear;
  
  return {
    lifePalace: analyzeLifePalace(chart),
    causePalace: analyzeCausePalace(chart),
    decade: analyzeDecade(chart, age),
    year: analyzeYear(new Date().getFullYear()),
    question: question ? answerQuestion(chart, question) : null
  };
}

// CLI 入口
if (require.main === module) {
  const chart = JSON.parse(process.argv[2] || '{}');
  const question = process.argv[3] || null;
  const report = generateReport(chart, question);
  console.log(JSON.stringify(report, null, 2));
}

module.exports = { generateReport, analyzeLifePalace, analyzeCausePalace };
