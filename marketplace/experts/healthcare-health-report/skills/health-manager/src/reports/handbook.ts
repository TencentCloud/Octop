import * as bloodPressure from '../database/bloodPressure';
import * as exercise from '../database/exercise';
import * as medication from '../database/medication';
import * as config from '../database/config';
import { formatDate, formatNumber, calculateBMI, getBMILevel, RESET_COLOR } from '../utils/format';

/**
 * 生成健康手册
 */
export function generateHealthHandbook(): string {
  const user = config.getUserConfig();
  const bpSummary = bloodPressure.getBloodPressureSummary();
  const exSummary = exercise.getExerciseSummary();
  const medSummary = medication.getMedicationSummary();
  const bpTrend30 = bloodPressure.getBloodPressureTrend(30);
  const exTrend30 = exercise.getExerciseTrend(30);

  const lines: string[] = [];

  // 封面
  lines.push('# 🏥 个人健康手册');
  lines.push('');
  lines.push(`**生成日期**: ${formatDate(new Date().toISOString())}`);
  lines.push('');
  lines.push('---');
  lines.push('');

  // 个人档案
  lines.push('# 一、个人档案');
  lines.push('');
  lines.push('| 项目 | 内容 |');
  lines.push('|------|------|');
  lines.push(`| 姓名 | ${user.name || '未设置'} |`);
  lines.push(`| 年龄 | ${user.age || '未设置'} |`);
  lines.push(`| 身高 | ${user.height ? user.height + ' cm' : '未设置'} |`);
  lines.push(`| 体重 | ${user.weight ? user.weight + ' kg' : '未设置'} |`);
  
  if (user.height && user.weight) {
    const bmi = calculateBMI(parseFloat(user.weight), parseFloat(user.height));
    const bmiLevel = getBMILevel(bmi);
    lines.push(`| BMI | ${formatNumber(bmi, 1)} (${bmiLevel.level}) |`);
  }
  lines.push('');

  // 数据概览
  lines.push('# 二、数据概览');
  lines.push('');
  lines.push('## 2.1 血压记录');
  lines.push(`- **总记录数**: ${bpSummary.total_records} 条`);
  lines.push(`- **记录天数**: ${bpSummary.total_days} 天`);
  lines.push(`- **首次记录**: ${bpSummary.first_record ? formatDate(bpSummary.first_record) : '无'}`);
  lines.push(`- **最近记录**: ${bpSummary.latest_record ? formatDate(bpSummary.latest_record) : '无'}`);
  lines.push('');

  lines.push('## 2.2 运动记录');
  lines.push(`- **总记录数**: ${exSummary.total_records} 条`);
  lines.push(`- **运动类型**: ${exSummary.exercise_types} 种`);
  lines.push(`- **总运动时长**: ${exSummary.total_duration} 分钟`);
  lines.push(`- **总步数**: ${exSummary.total_steps?.toLocaleString() || 0} 步`);
  lines.push(`- **总消耗**: ${formatNumber(exSummary.total_calories)} 千卡`);
  lines.push('');

  lines.push('## 2.3 用药记录');
  lines.push(`- **总记录数**: ${medSummary.total_records} 条`);
  lines.push(`- **药物种类**: ${medSummary.unique_medications} 种`);
  lines.push(`- **用药天数**: ${medSummary.total_days} 天`);
  lines.push('');

  // 30天趋势分析
  lines.push('# 三、30天趋势分析');
  lines.push('');

  lines.push('## 3.1 血压趋势');
  if (bpTrend30.record_count > 0) {
    lines.push(`- **平均收缩压**: ${formatNumber(bpTrend30.avg_systolic)} mmHg`);
    lines.push(`- **平均舒张压**: ${formatNumber(bpTrend30.avg_diastolic)} mmHg`);
    lines.push(`- **平均心率**: ${formatNumber(bpTrend30.avg_heart_rate)} bpm`);
    lines.push(`- **测量次数**: ${bpTrend30.record_count} 次`);
    
    const thresholds = config.getBloodPressureThresholds();
    if (bpTrend30.avg_systolic > thresholds.warningSystolic || 
        bpTrend30.avg_diastolic > thresholds.warningDiastolic) {
      lines.push('');
      lines.push('> ⚠️ **注意**: 近30天平均血压偏高，建议关注血压变化并咨询医生。');
    }
  } else {
    lines.push('*暂无近30天血压数据*');
  }
  lines.push('');

  lines.push('## 3.2 运动趋势');
  if (exTrend30.total_sessions > 0) {
    lines.push(`- **运动次数**: ${exTrend30.total_sessions} 次`);
    lines.push(`- **总时长**: ${exTrend30.total_duration} 分钟`);
    lines.push(`- **日均时长**: ${formatNumber(exTrend30.daily_avg_duration)} 分钟`);
    lines.push(`- **总步数**: ${exTrend30.total_steps?.toLocaleString() || 0} 步`);
    lines.push(`- **总消耗**: ${formatNumber(exTrend30.total_calories)} 千卡`);
    
    const goals = config.getExerciseGoals();
    const achievementRate = Math.min(100, Math.round((exTrend30.daily_avg_duration / goals.dailyDuration) * 100));
    lines.push(`- **目标达成率**: ${achievementRate}%`);
  } else {
    lines.push('*暂无近30天运动数据*');
  }
  lines.push('');

  // 健康建议
  lines.push('# 四、健康建议');
  lines.push('');
  lines.push('## 4.1 血压管理');
  lines.push('- 每天固定时间测量血压，建议早晚各一次');
  lines.push('- 测量前静坐5分钟，保持心情平静');
  lines.push('- 记录血压时同时记录心率，便于全面评估');
  lines.push('- 如发现血压持续偏高或偏低，及时就医');
  lines.push('');

  lines.push('## 4.2 运动建议');
  const goals = config.getExerciseGoals();
  lines.push(`- 建议每天运动至少 ${goals.dailyDuration} 分钟`);
  lines.push(`- 每日步数目标: ${goals.dailySteps.toLocaleString()} 步`);
  lines.push('- 选择自己喜欢的运动方式，保持运动习惯');
  lines.push('- 运动前后注意热身和放松');
  lines.push('- 循序渐进，避免过度运动');
  lines.push('');

  lines.push('## 4.3 用药管理');
  lines.push('- 按时服药，不要漏服或自行调整剂量');
  lines.push('- 记录每次服药情况，便于追踪');
  lines.push('- 如有不适或疑问，及时咨询医生或药师');
  lines.push('');

  // 数据记录
  lines.push('# 五、数据记录');
  lines.push('');
  lines.push('## 5.1 血压参考标准');
  lines.push('');
  lines.push('| 分类 | 收缩压(mmHg) | 舒张压(mmHg) |');
  lines.push('|------|-------------|-------------|');
  lines.push('| 正常 | < 120 | < 80 |');
  lines.push('| 正常偏高 | 120-129 | < 80 |');
  lines.push('| 高血压前期 | 130-139 | 80-89 |');
  lines.push('| 高血压1级 | 140-159 | 90-99 |');
  lines.push('| 高血压2级 | ≥ 160 | ≥ 100 |');
  lines.push('');

  lines.push('## 5.2 BMI参考标准');
  lines.push('');
  lines.push('| 分类 | BMI范围 |');
  lines.push('|------|---------|');
  lines.push('| 偏瘦 | < 18.5 |');
  lines.push('| 正常 | 18.5 - 23.9 |');
  lines.push('| 超重 | 24.0 - 27.9 |');
  lines.push('| 肥胖 | ≥ 28.0 |');
  lines.push('');

  // 附录
  lines.push('# 附录');
  lines.push('');
  lines.push('- 本手册基于您的健康数据自动生成');
  lines.push('- 建议定期查看并更新您的健康档案');
  lines.push('- 如有任何健康问题，请咨询专业医生');
  lines.push('');
  lines.push('---');
  lines.push('');
  lines.push('*本手册仅供参考，不能替代专业医疗建议*');

  return lines.join('\n');
}
