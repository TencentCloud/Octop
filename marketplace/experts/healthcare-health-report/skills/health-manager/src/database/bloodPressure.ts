import { getDatabase } from './connection';
import { BloodPressureRecord } from './schema';

const db = () => getDatabase();

/**
 * 添加血压记录
 */
export function addBloodPressure(record: BloodPressureRecord): number {
  const stmt = db().prepare(`
    INSERT INTO blood_pressure (systolic, diastolic, heart_rate, recorded_at, notes)
    VALUES (@systolic, @diastolic, @heart_rate, 
      COALESCE(@recorded_at, datetime('now')), @notes)
  `);
  const result = stmt.run(record);
  return result.lastInsertRowid as number;
}

/**
 * 获取血压记录列表
 */
export function getBloodPressureRecords(
  limit: number = 30,
  offset: number = 0
): BloodPressureRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM blood_pressure
    ORDER BY recorded_at DESC
    LIMIT @limit OFFSET @offset
  `);
  return stmt.all({ limit, offset }) as BloodPressureRecord[];
}

/**
 * 获取日期范围内的血压记录
 */
export function getBloodPressureByDateRange(
  startDate: string,
  endDate: string
): BloodPressureRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM blood_pressure
    WHERE recorded_at BETWEEN @startDate AND @endDate
    ORDER BY recorded_at ASC
  `);
  return stmt.all({ startDate, endDate }) as BloodPressureRecord[];
}

/**
 * 获取最近N天的血压记录
 */
export function getRecentBloodPressure(days: number): BloodPressureRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM blood_pressure
    WHERE recorded_at >= datetime('now', '-' || @days || ' days')
    ORDER BY recorded_at ASC
  `);
  return stmt.all({ days }) as BloodPressureRecord[];
}

/**
 * 计算血压趋势统计
 */
export function getBloodPressureTrend(days: number) {
  const stmt = db().prepare(`
    SELECT 
      ROUND(AVG(systolic), 1) as avg_systolic,
      ROUND(AVG(diastolic), 1) as avg_diastolic,
      ROUND(AVG(heart_rate), 1) as avg_heart_rate,
      MIN(systolic) as min_systolic,
      MAX(systolic) as max_systolic,
      MIN(diastolic) as min_diastolic,
      MAX(diastolic) as max_diastolic,
      COUNT(*) as record_count
    FROM blood_pressure
    WHERE recorded_at >= datetime('now', '-' || @days || ' days')
  `);
  return stmt.get({ days }) as {
    avg_systolic: number;
    avg_diastolic: number;
    avg_heart_rate: number;
    min_systolic: number;
    max_systolic: number;
    min_diastolic: number;
    max_diastolic: number;
    record_count: number;
  };
}

/**
 * 检测血压异常值
 */
export function detectAbnormalBloodPressure(
  systolicThreshold: number = 140,
  diastolicThreshold: number = 90
): BloodPressureRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM blood_pressure
    WHERE systolic >= @systolicThreshold 
       OR diastolic >= @diastolicThreshold
       OR systolic <= 90
       OR diastolic <= 60
    ORDER BY recorded_at DESC
    LIMIT 20
  `);
  return stmt.all({ systolicThreshold, diastolicThreshold }) as BloodPressureRecord[];
}

/**
 * 删除血压记录
 */
export function deleteBloodPressure(id: number): boolean {
  const stmt = db().prepare('DELETE FROM blood_pressure WHERE id = @id');
  const result = stmt.run({ id });
  return result.changes > 0;
}

/**
 * 获取血压统计摘要
 */
export function getBloodPressureSummary() {
  const stmt = db().prepare(`
    SELECT 
      COUNT(*) as total_records,
      COUNT(DISTINCT date(recorded_at)) as total_days,
      MIN(recorded_at) as first_record,
      MAX(recorded_at) as latest_record
    FROM blood_pressure
  `);
  return stmt.get() as {
    total_records: number;
    total_days: number;
    first_record: string;
    latest_record: string;
  };
}
