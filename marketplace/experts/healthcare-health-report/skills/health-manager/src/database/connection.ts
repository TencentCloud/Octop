import Database from 'better-sqlite3';
import path from 'path';
import os from 'os';
import fs from 'fs';
import { SCHEMA, DEFAULT_CONFIG } from './schema';
import { initDefaultReminders } from './reminders';

const DATA_DIR = path.join(os.homedir(), '.config', 'health-manager');
const DB_PATH = path.join(DATA_DIR, 'health.db');

let db: Database.Database | null = null;

/**
 * 初始化数据目录
 */
function initDataDir(): void {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
}

/**
 * 获取数据库连接
 */
export function getDatabase(): Database.Database {
  if (!db) {
    initDataDir();
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
    initializeSchema();
  }
  return db;
}

/**
 * 初始化数据库表结构
 */
function initializeSchema(): void {
  if (!db) return;

  // 创建表
  Object.values(SCHEMA).forEach(sql => {
    db!.exec(sql);
  });

  // 插入默认配置
  const insertConfig = db.prepare(`
    INSERT OR IGNORE INTO config (key, value, description)
    VALUES (@key, @value, @description)
  `);

  DEFAULT_CONFIG.forEach(config => {
    insertConfig.run(config);
  });

  // 初始化默认提醒
  initDefaultReminders();
}

/**
 * 关闭数据库连接
 */
export function closeDatabase(): void {
  if (db) {
    db.close();
    db = null;
  }
}

/**
 * 获取数据库文件路径
 */
export function getDatabasePath(): string {
  return DB_PATH;
}

export { initDefaultReminders };
