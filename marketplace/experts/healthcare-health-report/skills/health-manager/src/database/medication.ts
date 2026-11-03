import { getDatabase } from './connection';
import { MedicationRecord } from './schema';

const db = () => getDatabase();

/**
 * 添加用药记录
 */
export function addMedication(record: MedicationRecord): number {
  const stmt = db().prepare(`
    INSERT INTO medication (name, dosage, unit, taken_at, notes)
    VALUES (@name, @dosage, @unit, 
      COALESCE(@taken_at, datetime('now')), @notes)
  `);
  const result = stmt.run(record);
  return result.lastInsertRowid as number;
}

/**
 * 获取用药记录列表
 */
export function getMedicationRecords(
  limit: number = 30,
  offset: number = 0
): MedicationRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM medication
    ORDER BY taken_at DESC
    LIMIT @limit OFFSET @offset
  `);
  return stmt.all({ limit, offset }) as MedicationRecord[];
}

/**
 * 获取日期范围内的用药记录
 */
export function getMedicationByDateRange(
  startDate: string,
  endDate: string
): MedicationRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM medication
    WHERE taken_at BETWEEN @startDate AND @endDate
    ORDER BY taken_at ASC
  `);
  return stmt.all({ startDate, endDate }) as MedicationRecord[];
}

/**
 * 获取最近N天的用药记录
 */
export function getRecentMedication(days: number): MedicationRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM medication
    WHERE taken_at >= datetime('now', '-' || @days || ' days')
    ORDER BY taken_at ASC
  `);
  return stmt.all({ days }) as MedicationRecord[];
}

/**
 * 按药物名称统计
 */
export function getMedicationStats(days: number = 30) {
  const stmt = db().prepare(`
    SELECT 
      name,
      dosage,
      unit,
      COUNT(*) as taken_count,
      MAX(taken_at) as last_taken,
      MIN(taken_at) as first_taken
    FROM medication
    WHERE taken_at >= datetime('now', '-' || @days || ' days')
    GROUP BY name, dosage, unit
    ORDER BY taken_count DESC
  `);
  return stmt.all({ days }) as Array<{
    name: string;
    dosage: string;
    unit: string;
    taken_count: number;
    last_taken: string;
    first_taken: string;
  }>;
}

/**
 * 获取今日用药记录
 */
export function getTodayMedication(): MedicationRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM medication
    WHERE date(taken_at) = date('now')
    ORDER BY taken_at ASC
  `);
  return stmt.all() as MedicationRecord[];
}

/**
 * 删除用药记录
 */
export function deleteMedication(id: number): boolean {
  const stmt = db().prepare('DELETE FROM medication WHERE id = @id');
  const result = stmt.run({ id });
  return result.changes > 0;
}

/**
 * 获取用药统计摘要
 */
export function getMedicationSummary() {
  const stmt = db().prepare(`
    SELECT 
      COUNT(*) as total_records,
      COUNT(DISTINCT name) as unique_medications,
      COUNT(DISTINCT date(taken_at)) as total_days,
      MAX(taken_at) as last_medication
    FROM medication
  `);
  return stmt.get() as {
    total_records: number;
    unique_medications: number;
    total_days: number;
    last_medication: string;
  };
}
