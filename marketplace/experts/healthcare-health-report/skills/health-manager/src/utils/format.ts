/**
 * 格式化工具函数
 */

/**
 * 格式化日期时间
 */
export function formatDateTime(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

/**
 * 格式化日期
 */
export function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  });
}

/**
 * 格式化时间
 */
export function formatTime(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  });
}

/**
 * 获取当前日期时间字符串 (ISO格式)
 */
export function getCurrentDateTime(): string {
  return new Date().toISOString();
}

/**
 * 获取今天日期字符串
 */
export function getTodayString(): string {
  return new Date().toISOString().split('T')[0];
}

/**
 * 获取N天前的日期
 */
export function getDaysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().split('T')[0];
}

/**
 * 格式化数字（保留小数位）
 */
export function formatNumber(num: number | null | undefined, decimals: number = 1): string {
  if (num === null || num === undefined) return '-';
  return num.toFixed(decimals);
}

/**
 * 血压等级评估
 */
export function getBloodPressureLevel(systolic: number, diastolic: number): {
  level: string;
  color: string;
  advice: string;
} {
  if (systolic < 90 || diastolic < 60) {
    return {
      level: '偏低',
      color: '\x1b[33m', // 黄色
      advice: '血压偏低，如有头晕等症状请咨询医生'
    };
  }
  if (systolic < 120 && diastolic < 80) {
    return {
      level: '正常',
      color: '\x1b[32m', // 绿色
      advice: '血压正常，继续保持健康生活方式'
    };
  }
  if (systolic < 130 && diastolic < 80) {
    return {
      level: '正常偏高',
      color: '\x1b[36m', // 青色
      advice: '血压正常偏高，注意饮食和运动'
    };
  }
  if (systolic < 140 || diastolic < 90) {
    return {
      level: '高血压前期',
      color: '\x1b[33m', // 黄色
      advice: '血压偏高，建议改善生活方式并定期监测'
    };
  }
  if (systolic < 160 || diastolic < 100) {
    return {
      level: '高血压1级',
      color: '\x1b[35m', // 紫色
      advice: '血压偏高，建议就医咨询'
    };
  }
  return {
    level: '高血压2级',
    color: '\x1b[31m', // 红色
    advice: '血压较高，请及时就医'
  };
}

/**
 * 心率评估
 */
export function getHeartRateLevel(heartRate: number): {
  level: string;
  color: string;
} {
  if (heartRate < 60) {
    return { level: '偏慢', color: '\x1b[33m' };
  }
  if (heartRate <= 100) {
    return { level: '正常', color: '\x1b[32m' };
  }
  return { level: '偏快', color: '\x1b[33m' };
}

/**
 * 重置颜色
 */
export const RESET_COLOR = '\x1b[0m';

/**
 * BMI计算
 */
export function calculateBMI(weightKg: number, heightCm: number): number {
  const heightM = heightCm / 100;
  return weightKg / (heightM * heightM);
}

/**
 * BMI评估
 */
export function getBMILevel(bmi: number): {
  level: string;
  color: string;
} {
  if (bmi < 18.5) {
    return { level: '偏瘦', color: '\x1b[33m' };
  }
  if (bmi < 24) {
    return { level: '正常', color: '\x1b[32m' };
  }
  if (bmi < 28) {
    return { level: '超重', color: '\x1b[33m' };
  }
  return { level: '肥胖', color: '\x1b[31m' };
}
