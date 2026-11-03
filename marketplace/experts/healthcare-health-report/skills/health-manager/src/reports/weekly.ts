import * as bloodPressure from '../database/bloodPressure';
import * as exercise from '../database/exercise';
import * as medication from '../database/medication';
import * as config from '../database/config';
import { formatDate, formatNumber, RESET_COLOR } from '../utils/format';
import { renderTable, renderStatsCard } from '../utils/table';

/**
 * 生成周报
 */
export function generateWeeklyReport(endDate?: string): string {
  const end = endDate ? new Date(endDate) : new Date();
  const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000);
  
  const startStr = start.toISOString().split('T')[0];
  const endStr = end.toISOString().split('T')[0];

  const user = config.getUserConfig();
  const bpTrend = bloodPressure.getBloodPressureTrend(7);
  const exTrend = exercise.getExerciseTrend(7);
  const exByType = exercise.getExerciseStatsByType(7);
  const medStats = medication.getMedicationStats(7);

  const lines: string[] = [];
  lines.push(`# 健康周报`);
  lines.push(`**周期**: ${formatDate(startStr)} ~ ${formatDate(endStr)}`);
  if (user.name) {
    lines.push(`**用户**: ${user.name}`);
  }
  lines.push('');

  // 血压趋势
  lines.push('## 🩺 血压趋势 (7天)');
  if (bpTrend.record_count === 0) {
    lines.push('*本周暂无血压记录*');
  } else {
    lines.push(renderStatsCard('血压统计', {
      '测量次数': bpTrend.record_count,
      '平均收缩压': `${formatNumber(bpTrend.avg_systolic)} mmHg`,
      '平均舒张压': `${formatNumber(bpTrend.avg_diastolic)} mmHg`,
      '平均心率': `${formatNumber(bpTrend.avg_heart_rate)} bpm`,
      '收缩压范围': `${bpTrend.min_systolic} - ${bpTrend.max_systolic}`,
      '舒张压范围': `${bpTrend.min_diastolic} - ${bpTrend.max_diastolic}`
    }));
  }
  lines.push('');

  // 运动统计
  lines.push('## 🏃 运动统计 (7天)');
  if (exTrend.total_sessions === 0) {
    lines.push('*本周暂无运动记录*');
  } else {
    lines.push(renderStatsCard('运动概览', {
      '运动次数': exTrend.total_sessions,
      '总时长': `${exTrend.total_duration} 分钟`,
      '日均时长': `${formatNumber(exTrend.daily_avg_duration)} 分钟`,
      '总步数': exTrend.total_steps?.toLocaleString() || '-',
      '总消耗': `${formatNumber(exTrend.total_calories)} 千卡`
    }));
    lines.push('');

    if (exByType.length > 0) {
      lines.push('### 按运动类型统计');
      const typeRows = exByType.map(t => [
        t.type,
        t.count,
        `${t.total_duration}分钟`,
        t.total_steps?.toLocaleString() || '-',
        `${formatNumber(t.total_calories)}千卡`
      ]);
      lines.push(renderTable(['类型', '次数', '总时长', '总步数', '消耗'], typeRows));
    }
  }
  lines.push('');

  // 用药统计
  lines.push('## 💊 用药统计 (7天)');
  if (medStats.length === 0) {
    lines.push('*本周暂无用药记录*');
  } else {
    const medRows = medStats.map(m => [
      m.name,
      `${m.dosage}${m.unit || ''}`,
      m.taken_count,
      formatDate(m.last_taken)
    ]);
    lines.push(renderTable(['药物', '剂量', '服用次数', '最近服用'], medRows));
  }
  lines.push('');

  // 本周总结
  lines.push('## 📊 本周总结');
  const goals = config.getExerciseGoals();
  const exerciseDays = Math.floor(exTrend.total_duration / goals.dailyDuration);
  lines.push(`- 血压测量: ${bpTrend.record_count}次`);
  lines.push(`- 运动达标: ${exerciseDays}/7 天`);
  lines.push(`- 用药记录: ${medStats.reduce((sum, m) => sum + m.taken_count, 0)}次`);
  lines.push('');

  // 建议
  lines.push('## 💡 健康建议');
  if (bpTrend.record_count < 7) {
    lines.push('- 建议每天测量并记录血压，保持监测频率');
  }
  if (exerciseDays < 5) {
    lines.push('- 本周运动天数较少，建议增加运动频率');
  }
  if (bpTrend.avg_systolic > 140 || bpTrend.avg_diastolic > 90) {
    lines.push('- 本周平均血压偏高，建议咨询医生');
  }
  lines.push('');

  return lines.join('\n');
}
