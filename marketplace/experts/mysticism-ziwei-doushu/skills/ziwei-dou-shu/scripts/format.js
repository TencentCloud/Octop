#!/usr/bin/env node
/**
 * 格式化输出脚本
 */

function formatChart(chart, report) {
  const lines = [];
  
  lines.push('━━━━━━━━━━━━━━━━━━━━━━');
  lines.push('📊 紫微斗数命盘（北派飞星）');
  lines.push('━━━━━━━━━━━━━━━━━━━━━━');
  lines.push('');
  
  // 基本信息
  lines.push('【基本信息】');
  lines.push(`- 阳历：${chart.basic.solarDate} ${chart.basic.time}`);
  lines.push(`- 农历：${chart.basic.lunarDate}`);
  lines.push(`- 八字：${chart.fourPillars.year} ${chart.fourPillars.month} ${chart.fourPillars.day} ${chart.fourPillars.hour}`);
  lines.push(`- 生肖：${chart.basic.zodiac}`);
  lines.push(`- 星座：${chart.basic.constellation}`);
  lines.push(`- 五行局：${chart.basic.fiveElements}`);
  if (chart.basic.isZiHour) lines.push(`- 注：晚子时，按次日计算`);
  lines.push('');
  
  // 来因宫
  if (report.causePalace) {
    lines.push('【来因宫】' + report.causePalace.palace + `（${report.causePalace.stem}干）`);
    lines.push(`- ${report.causePalace.meaning}`);
    lines.push('');
  }
  
  // 命宫
  if (report.lifePalace) {
    lines.push('【命宫】在' + report.lifePalace.position + '宫');
    lines.push(`- 主星：${report.lifePalace.stars.join('、') || '无主星'}`);
    lines.push(`- 特质：${report.lifePalace.interpretation}`);
    lines.push(`- 类型：${report.lifePalace.personality}`);
    lines.push('');
  }
  
  // 十二宫
  lines.push('【十二宫速览】');
  chart.palaces.forEach(p => {
    const stars = p.majorStars.length > 0 ? p.majorStars.map(s => s.name).join('') : '无主星';
    const marker = chart.causePalace?.name === p.name ? ' ←来因宫' : '';
    lines.push(`${p.name.padEnd(4)} (${p.position})：${stars}${marker}`);
  });
  lines.push('');
  
  // 大限
  if (report.decade) {
    lines.push(`【当前大限】${report.decade.ageRange}`);
    lines.push(`- 大限宫：${report.decade.palace}`);
    lines.push(`- 重点：${report.decade.focus}`);
    lines.push(`- 建议：${report.decade.advice}`);
    lines.push('');
  }
  
  // 流年
  if (report.year) {
    lines.push(`【${report.year.year}流年】`);
    lines.push(`- 天干：${report.year.stem}`);
    lines.push(`- 重点：${report.year.focus}`);
    lines.push('');
  }
  
  // 问题解答
  if (report.question) {
    lines.push('【问题解答】');
    lines.push(`- ${report.question.palace}：${report.question.stars.join('、') || '无主星'}`);
    lines.push(`- 分析：${report.question.analysis}`);
    lines.push(`- 建议：${report.question.advice}`);
    lines.push('');
  }
  
  lines.push('━━━━━━━━━━━━━━━━━━━━━━');
  lines.push('💡 提示：北派飞星派分析，仅供参考');
  lines.push('━━━━━━━━━━━━━━━━━━━━━━');
  
  return lines.join('\n');
}

function formatDetailedReport(chart, report) {
  let md = '# 紫微斗数命盘分析报告\n\n';
  md += '**北派飞星派** | 生成时间：' + new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) + '\n\n';
  
  md += '## 一、基本信息\n\n';
  md += `- **阳历**：${chart.basic.solarDate} ${chart.basic.time}\n`;
  md += `- **农历**：${chart.basic.lunarDate}\n`;
  md += `- **八字**：${chart.fourPillars.year} ${chart.fourPillars.month} ${chart.fourPillars.day} ${chart.fourPillars.hour}\n`;
  md += `- **生肖**：${chart.basic.zodiac} | **星座**：${chart.basic.constellation}\n`;
  md += `- **五行局**：${chart.basic.fiveElements}\n\n`;
  
  md += '## 二、来因宫分析\n\n';
  if (report.causePalace) {
    md += `**来因宫**：${report.causePalace.palace}（${report.causePalace.stem}干）\n\n`;
    md += `${report.causePalace.meaning}\n\n`;
  }
  
  md += '## 三、命宫分析\n\n';
  if (report.lifePalace) {
    md += `**位置**：${report.lifePalace.position}宫\n\n`;
    md += `**主星**：${report.lifePalace.stars.join('、') || '无主星'}\n\n`;
    md += `**特质**：${report.lifePalace.interpretation}\n\n`;
    md += `**性格类型**：${report.lifePalace.personality}\n\n`;
  }
  
  md += '## 四、十二宫详解\n\n';
  chart.palaces.forEach((p, i) => {
    md += `### ${i+1}. ${p.name}\n\n`;
    md += `- **位置**：${p.position}\n`;
    md += `- **天干**：${p.heavenlyStem}\n`;
    if (p.majorStars.length > 0) {
      md += `- **主星**：${p.majorStars.map(s => s.name + (s.brightness ? `(${s.brightness})` : '')).join('、')}\n`;
    } else {
      md += `- **主星**：无（空宫，借对宫）\n`;
    }
    md += '\n';
  });
  
  md += '## 五、大限运势\n\n';
  if (report.decade) {
    md += `**当前大限**：${report.decade.ageRange}岁\n\n`;
    md += `- **大限宫**：${report.decade.palace}\n`;
    md += `- **重点**：${report.decade.focus}\n`;
    md += `- **建议**：${report.decade.advice}\n\n`;
  }
  
  md += '## 六、流年运势\n\n';
  if (report.year) {
    md += `**${report.year.year}年**（${report.year.stem}年）\n\n`;
    md += `**重点**：${report.year.focus}\n\n`;
  }
  
  if (report.question) {
    md += '## 七、问题解答\n\n';
    md += `**${report.question.type}**\n\n`;
    md += `- **宫位**：${report.question.palace}\n`;
    md += `- **星曜**：${report.question.stars.join('、') || '无主星'}\n`;
    md += `- **分析**：${report.question.analysis}\n`;
    md += `- **建议**：${report.question.advice}\n\n`;
  }
  
  md += '---\n\n';
  md += '> 💡 **提示**：本报告基于北派飞星派理论，仅供参考娱乐。\n';
  md += '> 命理是参考，人生掌握在自己手中。\n';
  
  return md;
}

if (require.main === module) {
  const chart = JSON.parse(process.argv[2] || '{}');
  const report = JSON.parse(process.argv[3] || '{}');
  const format = process.argv[4] || 'text';
  console.log(format === 'markdown' ? formatDetailedReport(chart, report) : formatChart(chart, report));
}

module.exports = { formatChart, formatDetailedReport };
