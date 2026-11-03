/**
 * 数据库表结构定义
 */

export const SCHEMA = {
  // 血压记录表
  bloodPressure: `
    CREATE TABLE IF NOT EXISTS blood_pressure (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      systolic INTEGER NOT NULL,          -- 收缩压
      diastolic INTEGER NOT NULL,         -- 舒张压
      heart_rate INTEGER,                 -- 心率
      recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 记录时间
      notes TEXT,                         -- 备注
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_bp_recorded_at ON blood_pressure(recorded_at);
  `,

  // 运动记录表
  exercise: `
    CREATE TABLE IF NOT EXISTS exercise (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      type TEXT NOT NULL,                 -- 运动类型 (walking, running, cycling, swimming, etc.)
      duration_minutes INTEGER NOT NULL,  -- 时长(分钟)
      steps INTEGER,                      -- 步数
      calories_burned REAL,               -- 消耗卡路里
      distance_km REAL,                   -- 距离(公里)
      recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      notes TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_exercise_recorded_at ON exercise(recorded_at);
    CREATE INDEX IF NOT EXISTS idx_exercise_type ON exercise(type);
  `,

  // 用药记录表
  medication: `
    CREATE TABLE IF NOT EXISTS medication (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,                 -- 药物名称
      dosage TEXT NOT NULL,               -- 剂量
      unit TEXT,                          -- 单位 (mg, ml, pill, etc.)
      taken_at DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 服药时间
      notes TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_medication_taken_at ON medication(taken_at);
    CREATE INDEX IF NOT EXISTS idx_medication_name ON medication(name);
  `,

  // 用户配置表
  config: `
    CREATE TABLE IF NOT EXISTS config (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      key TEXT UNIQUE NOT NULL,           -- 配置键
      value TEXT,                         -- 配置值
      description TEXT,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_config_key ON config(key);
  `,

  // 提醒配置表
  reminders: `
    CREATE TABLE IF NOT EXISTS reminders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      type TEXT NOT NULL,                 -- 提醒类型 (medication, bp_monitor, exercise)
      enabled BOOLEAN DEFAULT 1,          -- 是否启用
      schedule TEXT NOT NULL,             -- 提醒时间 (cron格式或HH:MM)
      message TEXT,                       -- 提醒消息
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_reminders_type ON reminders(type);
  `
};

// 默认配置
export const DEFAULT_CONFIG = [
  { key: 'user.name', value: '', description: '用户姓名' },
  { key: 'user.age', value: '', description: '用户年龄' },
  { key: 'user.height', value: '', description: '身高(cm)' },
  { key: 'user.weight', value: '', description: '体重(kg)' },
  { key: 'bp.normal_systolic', value: '120', description: '正常收缩压' },
  { key: 'bp.normal_diastolic', value: '80', description: '正常舒张压' },
  { key: 'bp.warning_systolic', value: '140', description: '警告收缩压' },
  { key: 'bp.warning_diastolic', value: '90', description: '警告舒张压' },
  { key: 'exercise.daily_goal', value: '30', description: '每日运动目标(分钟)' },
  { key: 'exercise.steps_goal', value: '10000', description: '每日步数目标' }
];

// 数据模型类型定义
export interface BloodPressureRecord {
  id?: number;
  systolic: number;
  diastolic: number;
  heart_rate?: number;
  recorded_at?: string;
  notes?: string;
}

export interface ExerciseRecord {
  id?: number;
  type: string;
  duration_minutes: number;
  steps?: number;
  calories_burned?: number;
  distance_km?: number;
  recorded_at?: string;
  notes?: string;
}

export interface MedicationRecord {
  id?: number;
  name: string;
  dosage: string;
  unit?: string;
  taken_at?: string;
  notes?: string;
}

export interface ConfigItem {
  id?: number;
  key: string;
  value: string;
  description?: string;
}

export interface ReminderConfig {
  id?: number;
  type: 'medication' | 'bp_monitor' | 'exercise';
  enabled: boolean;
  schedule: string;
  message?: string;
}
