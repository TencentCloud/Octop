import { table } from 'table';

/**
 * 表格配置
 */
const tableConfig = {
  border: {
    topBody: '─',
    topJoin: '┬',
    topLeft: '┌',
    topRight: '┐',
    bottomBody: '─',
    bottomJoin: '┴',
    bottomLeft: '└',
    bottomRight: '┘',
    bodyLeft: '│',
    bodyRight: '│',
    bodyJoin: '│',
    joinBody: '─',
    joinLeft: '├',
    joinRight: '┤',
    joinJoin: '┼'
  }
};

/**
 * 渲染数据表格
 */
export function renderTable(
  headers: string[],
  rows: (string | number | null | undefined)[][]
): string {
  if (rows.length === 0) {
    return '暂无数据';
  }

  const data = [
    headers,
    ...rows.map(row => row.map(cell => {
      if (cell === null || cell === undefined) return '-';
      return String(cell);
    }))
  ];

  return table(data, tableConfig);
}

/**
 * 渲染键值对表格
 */
export function renderKeyValueTable(
  data: Record<string, string | number | null | undefined>
): string {
  const rows = Object.entries(data).map(([key, value]) => [
    key,
    value === null || value === undefined ? '-' : String(value)
  ]);

  return table(rows, tableConfig);
}

/**
 * 渲染统计卡片
 */
export function renderStatsCard(
  title: string,
  stats: Record<string, string | number>
): string {
  const lines = [
    `┌${'─'.repeat(title.length + 2)}┐`,
    `│ ${title} │`,
    `├${'─'.repeat(title.length + 2)}┤`
  ];

  for (const [key, value] of Object.entries(stats)) {
    const line = `│ ${key}: ${value}`;
    const padding = title.length + 2 - line.length + 2;
    lines.push(line + ' '.repeat(Math.max(0, padding)) + '│');
  }

  lines.push(`└${'─'.repeat(title.length + 2)}┘`);
  return lines.join('\n');
}
