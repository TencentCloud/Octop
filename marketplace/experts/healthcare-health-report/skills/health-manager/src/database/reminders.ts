import { getDatabase } from './connection';
import { ReminderConfig } from './schema';

const db = () => getDatabase();

/**
 * 添加提醒配置
 */
export function addReminder(reminder: ReminderConfig): number {
  const stmt = db().prepare(`
    INSERT INTO reminders (type, enabled, schedule, message)
    VALUES (@type, @enabled, @schedule, @message)
  `);
  const result = stmt.run({
    type: reminder.type,
    enabled: reminder.enabled ? 1 : 0,
    schedule: reminder.schedule,
    message: reminder.message || ''
  });
  return result.lastInsertRowid as number;
}

/**
 * 获取所有提醒配置
 */
export function getAllReminders(): ReminderConfig[] {
  const stmt = db().prepare(`
    SELECT id, type, enabled as enabled, schedule, message
    FROM reminders
    ORDER BY type
  `);
  const rows = stmt.all() as Array<{
    id: number;
    type: string;
    enabled: number;
    schedule: string;
    message: string;
  }>;
  
  return rows.map(row => ({
    id: row.id,
    type: row.type as ReminderConfig['type'],
    enabled: Boolean(row.enabled),
    schedule: row.schedule,
    message: row.message
  }));
}

/**
 * 按类型获取提醒
 */
export function getRemindersByType(type: string): ReminderConfig[] {
  const stmt = db().prepare(`
    SELECT id, type, enabled as enabled, schedule, message
    FROM reminders
    WHERE type = @type
    ORDER BY schedule
  `);
  const rows = stmt.all({ type }) as Array<{
    id: number;
    type: string;
    enabled: number;
    schedule: string;
    message: string;
  }>;
  
  return rows.map(row => ({
    id: row.id,
    type: row.type as ReminderConfig['type'],
    enabled: Boolean(row.enabled),
    schedule: row.schedule,
    message: row.message
  }));
}

/**
 * 更新提醒配置
 */
export function updateReminder(
  id: number,
  updates: Partial<Omit<ReminderConfig, 'id' | 'type'>>
): boolean {
  const fields: string[] = [];
  const values: Record<string, any> = { id };

  if (updates.enabled !== undefined) {
    fields.push('enabled = @enabled');
    values.enabled = updates.enabled ? 1 : 0;
  }
  if (updates.schedule !== undefined) {
    fields.push('schedule = @schedule');
    values.schedule = updates.schedule;
  }
  if (updates.message !== undefined) {
    fields.push('message = @message');
    values.message = updates.message;
  }

  if (fields.length === 0) return false;

  fields.push('updated_at = datetime("now")');

  const stmt = db().prepare(`
    UPDATE reminders 
    SET ${fields.join(', ')}
    WHERE id = @id
  `);
  const result = stmt.run(values);
  return result.changes > 0;
}

/**
 * 删除提醒配置
 */
export function deleteReminder(id: number): boolean {
  const stmt = db().prepare('DELETE FROM reminders WHERE id = @id');
  const result = stmt.run({ id });
  return result.changes > 0;
}

/**
 * 切换提醒启用状态
 */
export function toggleReminder(id: number, enabled: boolean): boolean {
  const stmt = db().prepare(`
    UPDATE reminders 
    SET enabled = @enabled, updated_at = datetime('now')
    WHERE id = @id
  `);
  const result = stmt.run({ id, enabled: enabled ? 1 : 0 });
  return result.changes > 0;
}

/**
 * 初始化默认提醒
 */
export function initDefaultReminders(): void {
  const defaults = [
    {
      type: 'medication' as const,
      enabled: true,
      schedule: '08:00',
      message: '该吃药了，请按时服药'
    },
    {
      type: 'bp_monitor' as const,
      enabled: true,
      schedule: '09:00,21:00',
      message: '该测量血压了，请记录血压数据'
    },
    {
      type: 'exercise' as const,
      enabled: true,
      schedule: '18:00',
      message: '运动时间到了，今天运动了吗？'
    }
  ];

  const stmt = db().prepare(`
    INSERT OR IGNORE INTO reminders (type, enabled, schedule, message)
    VALUES (@type, @enabled, @schedule, @message)
  `);

  for (const reminder of defaults) {
    stmt.run({
      type: reminder.type,
      enabled: reminder.enabled ? 1 : 0,
      schedule: reminder.schedule,
      message: reminder.message
    });
  }
}
