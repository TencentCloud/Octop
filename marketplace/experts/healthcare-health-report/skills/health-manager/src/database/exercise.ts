import { getDatabase } from './connection';
import { ExerciseRecord } from './schema';

const db = () => getDatabase();

/**
 * 添加运动记录
 */
export function addExercise(record: ExerciseRecord): number {
  const stmt = db().prepare(`
    INSERT INTO exercise (type, duration_minutes, steps, calories_burned, distance_km, recorded_at, notes)
    VALUES (@type, @duration_minutes, @steps, @calories_burned, @distance_km,
      COALESCE(@recorded_at, datetime('now')), @notes)
  `);
  const result = stmt.run(record);
  return result.lastInsertRowid as number;
}

/**
 * 获取运动记录列表
 */
export function getExerciseRecords(
  limit: number = 30,
  offset: number = 0
): ExerciseRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM exercise
    ORDER BY recorded_at DESC
    LIMIT @limit OFFSET @offset
  `);
  return stmt.all({ limit, offset }) as ExerciseRecord[];
}

/**
 * 获取日期范围内的运动记录
 */
export function getExerciseByDateRange(
  startDate: string,
  endDate: string
): ExerciseRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM exercise
    WHERE recorded_at BETWEEN @startDate AND @endDate
    ORDER BY recorded_at ASC
  `);
  return stmt.all({ startDate, endDate }) as ExerciseRecord[];
}

/**
 * 获取最近N天的运动记录
 */
export function getRecentExercise(days: number): ExerciseRecord[] {
  const stmt = db().prepare(`
    SELECT * FROM exercise
    WHERE recorded_at >= datetime('now', '-' || @days || ' days')
    ORDER BY recorded_at ASC
  `);
  return stmt.all({ days }) as ExerciseRecord[];
}

/**
 * 按运动类型统计
 */
export function getExerciseStatsByType(days: number = 30) {
  const stmt = db().prepare(`
    SELECT 
      type,
      COUNT(*) as count,
      SUM(duration_minutes) as total_duration,
      SUM(steps) as total_steps,
      SUM(calories_burned) as total_calories,
      SUM(distance_km) as total_distance
    FROM exercise
    WHERE recorded_at >= datetime('now', '-' || @days || ' days')
    GROUP BY type
    ORDER BY total_duration DESC
  `);
  return stmt.all({ days }) as Array<{
    type: string;
    count: number;
    total_duration: number;
    total_steps: number;
    total_calories: number;
    total_distance: number;
  }>;
}

/**
 * 获取每日运动统计
 */
export function getDailyExerciseStats(days: number = 30) {
  const stmt = db().prepare(`
    SELECT 
      date(recorded_at) as date,
      SUM(duration_minutes) as total_duration,
      SUM(steps) as total_steps,
      SUM(calories_burned) as total_calories,
      COUNT(*) as session_count
    FROM exercise
    WHERE recorded_at >= datetime('now', '-' || @days || ' days')
    GROUP BY date(recorded_at)
    ORDER BY date DESC
  `);
  return stmt.all({ days }) as Array<{
    date: string;
    total_duration: number;
    total_steps: number;
    total_calories: number;
    session_count: number;
  }>;
}

/**
 * 获取运动趋势统计
 */
export function getExerciseTrend(days: number) {
  const stmt = db().prepare(`
    SELECT 
      COUNT(*) as total_sessions,
      SUM(duration_minutes) as total_duration,
      SUM(steps) as total_steps,
      SUM(calories_burned) as total_calories,
      AVG(duration_minutes) as avg_duration,
      ROUND(SUM(duration_minutes) * 1.0 / @days, 1) as daily_avg_duration
    FROM exercise
    WHERE recorded_at >= datetime('now', '-' || @days || ' days')
  `);
  return stmt.get({ days }) as {
    total_sessions: number;
    total_duration: number;
    total_steps: number;
    total_calories: number;
    avg_duration: number;
    daily_avg_duration: number;
  };
}

/**
 * 删除运动记录
 */
export function deleteExercise(id: number): boolean {
  const stmt = db().prepare('DELETE FROM exercise WHERE id = @id');
  const result = stmt.run({ id });
  return result.changes > 0;
}

/**
 * 获取运动统计摘要
 */
export function getExerciseSummary() {
  const stmt = db().prepare(`
    SELECT 
      COUNT(*) as total_records,
      SUM(duration_minutes) as total_duration,
      SUM(steps) as total_steps,
      SUM(calories_burned) as total_calories,
      COUNT(DISTINCT type) as exercise_types
    FROM exercise
  `);
  return stmt.get() as {
    total_records: number;
    total_duration: number;
    total_steps: number;
    total_calories: number;
    exercise_types: number;
  };
}
