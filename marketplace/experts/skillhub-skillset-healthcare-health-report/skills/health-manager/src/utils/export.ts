import fs from 'fs';
import path from 'path';
import { getDatabase } from '../database/connection';

/**
 * 导出数据为CSV格式
 */
export function exportToCSV(
  tableName: string,
  outputPath?: string
): string {
  const db = getDatabase();
  const records = db.prepare(`SELECT * FROM ${tableName}`).all();

  if (records.length === 0) {
    throw new Error(`表 ${tableName} 没有数据`);
  }

  const headers = Object.keys(records[0] as object);
  const csvRows = [headers.join(',')];

  for (const record of records) {
    const values = headers.map(h => {
      const value = (record as Record<string, any>)[h];
      if (value === null || value === undefined) return '';
      // 处理包含逗号或引号的值
      const str = String(value);
      if (str.includes(',') || str.includes('"') || str.includes('\n')) {
        return `"${str.replace(/"/g, '""')}"`;
      }
      return str;
    });
    csvRows.push(values.join(','));
  }

  const csvContent = csvRows.join('\n');

  if (outputPath) {
    fs.writeFileSync(outputPath, csvContent, 'utf-8');
    return outputPath;
  }

  return csvContent;
}

/**
 * 导出数据为JSON格式
 */
export function exportToJSON(
  tableName: string,
  outputPath?: string
): string {
  const db = getDatabase();
  const records = db.prepare(`SELECT * FROM ${tableName}`).all();

  const jsonContent = JSON.stringify(records, null, 2);

  if (outputPath) {
    fs.writeFileSync(outputPath, jsonContent, 'utf-8');
    return outputPath;
  }

  return jsonContent;
}

/**
 * 导出所有数据
 */
export function exportAllData(outputDir: string): string[] {
  const tables = ['blood_pressure', 'exercise', 'medication', 'config'];
  const exported: string[] = [];

  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');

  for (const table of tables) {
    const csvPath = path.join(outputDir, `${table}_${timestamp}.csv`);
    exportToCSV(table, csvPath);
    exported.push(csvPath);

    const jsonPath = path.join(outputDir, `${table}_${timestamp}.json`);
    exportToJSON(table, jsonPath);
    exported.push(jsonPath);
  }

  return exported;
}

/**
 * 从CSV导入数据
 */
export function importFromCSV(
  tableName: string,
  csvPath: string
): number {
  const db = getDatabase();
  const content = fs.readFileSync(csvPath, 'utf-8');
  const lines = content.trim().split('\n');

  if (lines.length < 2) {
    throw new Error('CSV文件格式不正确');
  }

  const headers = lines[0].split(',').map(h => h.trim());
  let imported = 0;

  const placeholders = headers.map(() => '?').join(', ');
  const stmt = db.prepare(`
    INSERT INTO ${tableName} (${headers.join(', ')})
    VALUES (${placeholders})
  `);

  const insertMany = db.transaction((rows) => {
    for (const row of rows) {
      stmt.run(row);
    }
    return rows.length;
  });

  const rows: any[][] = [];
  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i]);
    rows.push(values);
  }

  return insertMany(rows);
}

/**
 * 从JSON导入数据
 */
export function importFromJSON(
  tableName: string,
  jsonPath: string
): number {
  const db = getDatabase();
  const content = fs.readFileSync(jsonPath, 'utf-8');
  const records = JSON.parse(content) as Record<string, any>[];

  if (records.length === 0) {
    return 0;
  }

  const headers = Object.keys(records[0]).filter(h => h !== 'id');
  const placeholders = headers.map(() => '?').join(', ');
  
  const stmt = db.prepare(`
    INSERT INTO ${tableName} (${headers.join(', ')})
    VALUES (${placeholders})
  `);

  const insertMany = db.transaction((rows) => {
    for (const row of rows) {
      stmt.run(row);
    }
    return rows.length;
  });

  const rows = records.map(record => 
    headers.map(h => record[h] ?? null)
  );

  return insertMany(rows);
}

/**
 * 解析CSV行（处理引号）
 */
function parseCSVLine(line: string): string[] {
  const values: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    const nextChar = line[i + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        current += '"';
        i++; // 跳过下一个引号
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      values.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }

  values.push(current.trim());
  return values;
}
