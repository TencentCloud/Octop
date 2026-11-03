import { getDatabase } from './connection';
import { ConfigItem } from './schema';

const db = () => getDatabase();

/**
 * 获取配置值
 */
export function getConfig(key: string): string | undefined {
  const stmt = db().prepare('SELECT value FROM config WHERE key = @key');
  const result = stmt.get({ key }) as { value: string } | undefined;
  return result?.value;
}

/**
 * 设置配置值
 */
export function setConfig(key: string, value: string): boolean {
  const stmt = db().prepare(`
    UPDATE config 
    SET value = @value, updated_at = datetime('now')
    WHERE key = @key
  `);
  const result = stmt.run({ key, value });
  return result.changes > 0;
}

/**
 * 获取所有配置
 */
export function getAllConfig(): ConfigItem[] {
  const stmt = db().prepare(`
    SELECT id, key, value, description FROM config
    ORDER BY key
  `);
  return stmt.all() as ConfigItem[];
}

/**
 * 获取配置分组
 */
export function getConfigByPrefix(prefix: string): ConfigItem[] {
  const stmt = db().prepare(`
    SELECT id, key, value, description FROM config
    WHERE key LIKE @prefix || '%'
    ORDER BY key
  `);
  return stmt.all({ prefix }) as ConfigItem[];
}

/**
 * 批量更新配置
 */
export function batchUpdateConfig(items: { key: string; value: string }[]): number {
  const stmt = db().prepare(`
    UPDATE config 
    SET value = @value, updated_at = datetime('now')
    WHERE key = @key
  `);
  
  const updateMany = db().transaction((items) => {
    let count = 0;
    for (const item of items) {
      const result = stmt.run(item);
      count += result.changes;
    }
    return count;
  });

  return updateMany(items);
}

/**
 * 初始化用户配置
 */
export function initUserConfig(config: {
  name?: string;
  age?: string;
  height?: string;
  weight?: string;
}): void {
  const items = [];
  if (config.name !== undefined) items.push({ key: 'user.name', value: config.name });
  if (config.age !== undefined) items.push({ key: 'user.age', value: config.age });
  if (config.height !== undefined) items.push({ key: 'user.height', value: config.height });
  if (config.weight !== undefined) items.push({ key: 'user.weight', value: config.weight });
  
  if (items.length > 0) {
    batchUpdateConfig(items);
  }
}

/**
 * 获取用户配置对象
 */
export function getUserConfig() {
  return {
    name: getConfig('user.name') || '',
    age: getConfig('user.age') || '',
    height: getConfig('user.height') || '',
    weight: getConfig('user.weight') || ''
  };
}

/**
 * 获取血压阈值配置
 */
export function getBloodPressureThresholds() {
  return {
    normalSystolic: parseInt(getConfig('bp.normal_systolic') || '120'),
    normalDiastolic: parseInt(getConfig('bp.normal_diastolic') || '80'),
    warningSystolic: parseInt(getConfig('bp.warning_systolic') || '140'),
    warningDiastolic: parseInt(getConfig('bp.warning_diastolic') || '90')
  };
}

/**
 * 获取运动目标配置
 */
export function getExerciseGoals() {
  return {
    dailyDuration: parseInt(getConfig('exercise.daily_goal') || '30'),
    dailySteps: parseInt(getConfig('exercise.steps_goal') || '10000')
  };
}
