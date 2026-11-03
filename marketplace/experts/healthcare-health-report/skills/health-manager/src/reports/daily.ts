import { getDatabase } from '../database/connection';
import * as bloodPressure from '../database/bloodPressure';
import * as exercise from '../database/exercise';
import * as medication from '../database/medication';
import * as config from '../database/config';
import { formatDate, formatNumber, getBloodPressureLevel, RESET_COLOR } from '../utils/format';
import { renderTable, renderStatsCard } from '../utils/table';

/**
 * 生成日报
 */
export function generateDailyReport(date?: string): string {
  const targetDate = date || new Date().toISOString().split('T')[0];
  const nextDate = new Date(new Date(targetDate).getTime() + 24 * 60 * 60 * 1000)
    .toISOString().split('T')[0];

  const user = config.getUserConfig();
  const bpRecords = bloodPressure.getBloodPressureByDateRange(targetDate, nextDate);
  const exRecords = exercise.getExerciseByDateRange(targetDate, nextDate);
  const medRecords = medication.getMedicationByDateRange(targetDate, nextDate);

  const lines: string[] = [];
  lines.push(`# 健康日报 - ${formatDate(targetDate)}`);
  lines.push('');

  // 用户信息
  if (user.name) {
    lines.push(`**用户**: ${user.name}`);
  }
  lines.push('');

  // 血压摘要
  lines.push('## 🩺 血压记录');
  if (bpRecords.length === 0) {
    lines.push('*今日暂无血压记录*');
  } else {
    const bpRows = bpRecords.map(r => {
      const level = getBloodPressureLevel(r.systolic, r.diastolic);
      return [
        r.recorded_at ? formatDate(r.recorded_at).split(' ')[1] : '-',
        `${r.systolic}/${r.diastolic}`,
        r.heart_rate || '-',
        `${level.color}${level.level}${RESET_COLOR}`,
        r.notes || '-'
      ];
    });
    lines.push(renderTable(['时间', '血压(mmHg)', '心率', '状态', '备注'], bpRows));
    
    // 计算平均值
    const avgSystolic = bpRecords.reduce((sum, r) => sum + r.systolic, 0) / bpRecords.length;
    const avgDiastolic = bpRecords.reduce((sum, r) => sum + r.diastolic, 0) / bpRecords.length;
    const avgHeartRate = bpRecords.filter(r => r.heart_rate).reduce((sum, r) => sum + (r.heart_rate || 0), 0) / 
      bpRecords.filter(r => r.heart_rate).length || 0;
    
    lines.push('');
    lines.push(`**今日平均**: ${formatNumber(avgSystolic, 0)}/${formatNumber(avgDiastolic, 0)} mmHg`);
    if (avgHeartRate > 0) {
      lines.push(`**平均心率**: ${formatNumber(avgHeartRate, 0)} bpm`);
    }
  }
  lines.push('');

  // 运动摘要
  lines.push('## 🏃 运动记录');
  if (exRecords.length === 0) {
    lines.push('*今日暂无运动记录*');
  } else {
    const exRows = exRecords.map(r => [
      r.type,
      `${r.duration_minutes}分钟`,
      r.steps || '-',
      r.calories_burned ? `${formatNumber(r.calories_burned)}千卡` : '-',
      r.notes || '-'
    ]);
    lines.push(renderTable(['类型', '时长', '步数', '消耗', '备注'], exRows));
    
    const totalDuration = exRecords.reduce((sum, r) => sum + r.duration_minutes, 0);
    const totalSteps = exRecords.reduce((sum, r) => sum + (r.steps || 0), 0);
    const totalCalories = exRecords.reduce((sum, r) => sum + (r.calories_burned || 0), 0);
    
    lines.push('');
    lines.push(`**今日总计**: ${totalDuration}分钟 | ${totalSteps}步 | ${formatNumber(totalCalories)}千卡`);
    
    // 检查目标
    const goals = config.getExerciseGoals();
    lines.push(`**运动目标**: ${totalDuration >= goals.dailyDuration ? '✅' : '❌'} ${totalDuration}/${goals.dailyDuration}分钟`);
    lines.push(`**步数目标**: ${totalSteps >= goals.dailySteps ? '✅' : '❌'} ${totalSteps}/${goals.dailySteps}步`);
  }
  lines.push('');

  // 用药摘要
  lines.push('## 💊 用药记录');
  if (medRecords.length === 0) {
    lines.push('*今日暂无用药记录*');
  } else {
    const medRows = medRecords.map(r => [
      r.name,
      `${r.dosage}${r.unit || ''}`,
      r.taken_at ? formatDate(r.taken_at).split(' ')[1] : '-',
      r.notes || '-'
    ]);
    lines.push(renderTable(['药物', '剂量', '时间', '备注'], medRows));
  }
  lines.push('');

  // 健康提示
  lines.push('## 💡 健康提示');
  if (bpRecords.length > 0) {
    const lastBP = bpRecords[bpRecords.length - 1];
    const level = getBloodPressureLevel(lastBP.systolic, lastBP.diastolic);
    lines.push(`- 血压状态: ${level.level} - ${level.advice}`);
  }
  if (exRecords.length === 0) {
    lines.push('- 今日尚未记录运动，建议适当活动');
  }
  lines.push('');

  return lines.join('\n');
}
