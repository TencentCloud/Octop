#!/usr/bin/env node

import { Command } from 'commander';
import chalk from 'chalk';
import * as bloodPressure from './database/bloodPressure';
import * as exercise from './database/exercise';
import * as medication from './database/medication';
import * as config from './database/config';
import * as reminders from './database/reminders';
import { getDatabasePath, closeDatabase, initDefaultReminders } from './database/connection';
import { generateDailyReport, generateWeeklyReport, generateHealthHandbook } from './reports';
import { exportToCSV, exportToJSON, exportAllData, importFromCSV, importFromJSON } from './utils/export';
import { renderTable } from './utils/table';
import { formatDateTime, formatDate, getBloodPressureLevel, getHeartRateLevel, RESET_COLOR } from './utils/format';
import fs from 'fs';
import path from 'path';

const program = new Command();

program
  .name('health')
  .description('健康管理 CLI 工具')
  .version('1.0.0');

// ========== 血压管理命令 ==========
const bpCmd = program.command('bp').description('血压管理');

bpCmd
  .command('add <systolic> <diastolic>')
  .description('添加血压记录')
  .option('-r, --heart-rate <rate>', '心率')
  .option('-n, --notes <notes>', '备注')
  .option('-d, --date <date>', '记录时间 (ISO格式)')
  .action((systolic, diastolic, options) => {
    const id = bloodPressure.addBloodPressure({
      systolic: parseInt(systolic),
      diastolic: parseInt(diastolic),
      heart_rate: options.heartRate ? parseInt(options.heartRate) : undefined,
      recorded_at: options.date,
      notes: options.notes
    });
    
    const level = getBloodPressureLevel(parseInt(systolic), parseInt(diastolic));
    console.log(chalk.green(`✓ 血压记录已添加 (ID: ${id})`));
    console.log(`  血压: ${systolic}/${diastolic} mmHg ${level.color}[${level.level}]${RESET_COLOR}`);
    if (options.heartRate) {
      const hrLevel = getHeartRateLevel(parseInt(options.heartRate));
      console.log(`  心率: ${options.heartRate} bpm ${hrLevel.color}[${hrLevel.level}]${RESET_COLOR}`);
    }
    closeDatabase();
  });

bpCmd
  .command('list')
  .description('查看血压记录')
  .option('-l, --limit <n>', '显示条数', '10')
  .action((options) => {
    const records = bloodPressure.getBloodPressureRecords(parseInt(options.limit));
    const rows = records.map(r => {
      const level = getBloodPressureLevel(r.systolic, r.diastolic);
      return [
        r.id,
        `${r.systolic}/${r.diastolic}`,
        r.heart_rate || '-',
        `${level.color}${level.level}${RESET_COLOR}`,
        r.recorded_at ? formatDateTime(r.recorded_at) : '-',
        r.notes || '-'
      ];
    });
    console.log(renderTable(['ID', '血压', '心率', '状态', '时间', '备注'], rows));
    closeDatabase();
  });

bpCmd
  .command('trend [days]')
  .description('查看血压趋势')
  .action((days = '7') => {
    const trend = bloodPressure.getBloodPressureTrend(parseInt(days));
    console.log(chalk.blue(`📊 近${days}天血压趋势`));
    console.log(`  平均收缩压: ${trend.avg_systolic || '-'} mmHg`);
    console.log(`  平均舒张压: ${trend.avg_diastolic || '-'} mmHg`);
    console.log(`  平均心率: ${trend.avg_heart_rate || '-'} bpm`);
    console.log(`  记录次数: ${trend.record_count} 次`);
    closeDatabase();
  });

bpCmd
  .command('abnormal')
  .description('查看异常血压记录')
  .action(() => {
    const records = bloodPressure.detectAbnormalBloodPressure();
    if (records.length === 0) {
      console.log(chalk.green('✓ 未发现异常血压记录'));
    } else {
      const rows = records.map(r => [
        r.id,
        `${r.systolic}/${r.diastolic}`,
        r.heart_rate || '-',
        r.recorded_at ? formatDateTime(r.recorded_at) : '-',
        r.notes || '-'
      ]);
      console.log(chalk.yellow(`⚠ 发现 ${records.length} 条异常记录:`));
      console.log(renderTable(['ID', '血压', '心率', '时间', '备注'], rows));
    }
    closeDatabase();
  });

// ========== 运动管理命令 ==========
const exCmd = program.command('ex').description('运动管理');

exCmd
  .command('add <type> <duration>')
  .description('添加运动记录')
  .option('-s, --steps <steps>', '步数')
  .option('-c, --calories <cal>', '消耗卡路里')
  .option('-d, --distance <km>', '距离(公里)')
  .option('-n, --notes <notes>', '备注')
  .option('-t, --time <time>', '记录时间')
  .action((type, duration, options) => {
    const id = exercise.addExercise({
      type,
      duration_minutes: parseInt(duration),
      steps: options.steps ? parseInt(options.steps) : undefined,
      calories_burned: options.calories ? parseFloat(options.calories) : undefined,
      distance_km: options.distance ? parseFloat(options.distance) : undefined,
      recorded_at: options.time,
      notes: options.notes
    });
    console.log(chalk.green(`✓ 运动记录已添加 (ID: ${id})`));
    console.log(`  类型: ${type}, 时长: ${duration}分钟`);
    closeDatabase();
  });

exCmd
  .command('list')
  .description('查看运动记录')
  .option('-l, --limit <n>', '显示条数', '10')
  .action((options) => {
    const records = exercise.getExerciseRecords(parseInt(options.limit));
    const rows = records.map(r => [
      r.id,
      r.type,
      `${r.duration_minutes}分钟`,
      r.steps || '-',
      r.calories_burned ? `${r.calories_burned}千卡` : '-',
      r.recorded_at ? formatDateTime(r.recorded_at) : '-'
    ]);
    console.log(renderTable(['ID', '类型', '时长', '步数', '消耗', '时间'], rows));
    closeDatabase();
  });

exCmd
  .command('stats [days]')
  .description('查看运动统计')
  .action((days = '7') => {
    const trend = exercise.getExerciseTrend(parseInt(days));
    const byType = exercise.getExerciseStatsByType(parseInt(days));
    
    console.log(chalk.blue(`📊 近${days}天运动统计`));
    console.log(`  总次数: ${trend.total_sessions} 次`);
    console.log(`  总时长: ${trend.total_duration} 分钟`);
    console.log(`  日均: ${trend.daily_avg_duration?.toFixed(1) || 0} 分钟`);
    console.log(`  总步数: ${trend.total_steps?.toLocaleString() || 0}`);
    console.log(`  总消耗: ${trend.total_calories?.toFixed(0) || 0} 千卡`);
    
    if (byType.length > 0) {
      console.log('\n按类型统计:');
      const rows = byType.map(t => [t.type, t.count, `${t.total_duration}分钟`]);
      console.log(renderTable(['类型', '次数', '时长'], rows));
    }
    closeDatabase();
  });

// ========== 用药管理命令 ==========
const medCmd = program.command('med').description('用药管理');

medCmd
  .command('add <name> <dosage>')
  .description('添加用药记录')
  .option('-u, --unit <unit>', '单位')
  .option('-t, --time <time>', '服药时间')
  .option('-n, --notes <notes>', '备注')
  .action((name, dosage, options) => {
    const id = medication.addMedication({
      name,
      dosage,
      unit: options.unit,
      taken_at: options.time,
      notes: options.notes
    });
    console.log(chalk.green(`✓ 用药记录已添加 (ID: ${id})`));
    console.log(`  药物: ${name}, 剂量: ${dosage}${options.unit || ''}`);
    closeDatabase();
  });

medCmd
  .command('list')
  .description('查看用药记录')
  .option('-l, --limit <n>', '显示条数', '10')
  .action((options) => {
    const records = medication.getMedicationRecords(parseInt(options.limit));
    const rows = records.map(r => [
      r.id,
      r.name,
      `${r.dosage}${r.unit || ''}`,
      r.taken_at ? formatDateTime(r.taken_at) : '-',
      r.notes || '-'
    ]);
    console.log(renderTable(['ID', '药物', '剂量', '时间', '备注'], rows));
    closeDatabase();
  });

medCmd
  .command('today')
  .description('查看今日用药')
  .action(() => {
    const records = medication.getTodayMedication();
    if (records.length === 0) {
      console.log(chalk.yellow('今日暂无用药记录'));
    } else {
      const rows = records.map(r => [
        r.name,
        `${r.dosage}${r.unit || ''}`,
        r.taken_at ? formatDateTime(r.taken_at).split(' ')[1] : '-'
      ]);
      console.log(renderTable(['药物', '剂量', '时间'], rows));
    }
    closeDatabase();
  });

// ========== 报告生成命令 ==========
const reportCmd = program.command('report').description('报告生成');

reportCmd
  .command('daily [date]')
  .description('生成日报')
  .option('-o, --output <path>', '输出文件路径')
  .action((date, options) => {
    const report = generateDailyReport(date);
    if (options.output) {
      fs.writeFileSync(options.output, report, 'utf-8');
      console.log(chalk.green(`✓ 日报已保存至: ${options.output}`));
    } else {
      console.log(report);
    }
    closeDatabase();
  });

reportCmd
  .command('weekly [endDate]')
  .description('生成周报')
  .option('-o, --output <path>', '输出文件路径')
  .action((endDate, options) => {
    const report = generateWeeklyReport(endDate);
    if (options.output) {
      fs.writeFileSync(options.output, report, 'utf-8');
      console.log(chalk.green(`✓ 周报已保存至: ${options.output}`));
    } else {
      console.log(report);
    }
    closeDatabase();
  });

reportCmd
  .command('handbook')
  .description('生成健康手册')
  .option('-o, --output <path>', '输出文件路径')
  .action((options) => {
    const report = generateHealthHandbook();
    if (options.output) {
      fs.writeFileSync(options.output, report, 'utf-8');
      console.log(chalk.green(`✓ 健康手册已保存至: ${options.output}`));
    } else {
      console.log(report);
    }
    closeDatabase();
  });

// ========== 数据导出导入命令 ==========
const dataCmd = program.command('data').description('数据管理');

dataCmd
  .command('export <table>')
  .description('导出数据')
  .option('-f, --format <format>', '导出格式 (csv/json)', 'csv')
  .option('-o, --output <path>', '输出文件路径')
  .action((table, options) => {
    const validTables = ['blood_pressure', 'exercise', 'medication', 'config'];
    if (!validTables.includes(table)) {
      console.log(chalk.red(`错误: 无效的表名. 可选: ${validTables.join(', ')}`));
      return;
    }
    
    try {
      if (options.format === 'json') {
        const result = exportToJSON(table, options.output);
        if (options.output) {
          console.log(chalk.green(`✓ 数据已导出至: ${options.output}`));
        } else {
          console.log(result);
        }
      } else {
        const result = exportToCSV(table, options.output);
        if (options.output) {
          console.log(chalk.green(`✓ 数据已导出至: ${options.output}`));
        } else {
          console.log(result);
        }
      }
    } catch (err: any) {
      console.log(chalk.red(`导出失败: ${err.message}`));
    }
    closeDatabase();
  });

dataCmd
  .command('export-all <dir>')
  .description('导出所有数据')
  .action((dir) => {
    try {
      const files = exportAllData(dir);
      console.log(chalk.green(`✓ 所有数据已导出:`));
      files.forEach(f => console.log(`  - ${f}`));
    } catch (err: any) {
      console.log(chalk.red(`导出失败: ${err.message}`));
    }
    closeDatabase();
  });

dataCmd
  .command('import <table> <file>')
  .description('导入数据')
  .action((table, file) => {
    const validTables = ['blood_pressure', 'exercise', 'medication'];
    if (!validTables.includes(table)) {
      console.log(chalk.red(`错误: 无效的表名. 可选: ${validTables.join(', ')}`));
      return;
    }
    
    try {
      const ext = path.extname(file).toLowerCase();
      let count: number;
      
      if (ext === '.json') {
        count = importFromJSON(table, file);
      } else if (ext === '.csv') {
        count = importFromCSV(table, file);
      } else {
        console.log(chalk.red('错误: 不支持的文件格式，请使用 .csv 或 .json'));
        return;
      }
      
      console.log(chalk.green(`✓ 成功导入 ${count} 条记录`));
    } catch (err: any) {
      console.log(chalk.red(`导入失败: ${err.message}`));
    }
    closeDatabase();
  });

dataCmd
  .command('path')
  .description('显示数据库路径')
  .action(() => {
    console.log(chalk.blue('数据库位置:'));
    console.log(`  ${getDatabasePath()}`);
    closeDatabase();
  });

// ========== 配置管理命令 ==========
const configCmd = program.command('config').description('配置管理');

configCmd
  .command('list')
  .description('查看所有配置')
  .action(() => {
    const configs = config.getAllConfig();
    const rows = configs.map(c => [c.key, c.value || '(空)', c.description || '-']);
    console.log(renderTable(['配置项', '值', '说明'], rows));
    closeDatabase();
  });

configCmd
  .command('set <key> <value>')
  .description('设置配置项')
  .action((key, value) => {
    config.setConfig(key, value);
    console.log(chalk.green(`✓ 配置已更新: ${key} = ${value}`));
    closeDatabase();
  });

configCmd
  .command('init')
  .description('初始化用户配置')
  .option('-n, --name <name>', '姓名')
  .option('-a, --age <age>', '年龄')
  .option('-h, --height <height>', '身高(cm)')
  .option('-w, --weight <weight>', '体重(kg)')
  .action((options) => {
    config.initUserConfig({
      name: options.name,
      age: options.age,
      height: options.height,
      weight: options.weight
    });
    console.log(chalk.green('✓ 用户配置已更新'));
    closeDatabase();
  });

// ========== 提醒管理命令 ==========
const reminderCmd = program.command('reminder').description('提醒管理');

reminderCmd
  .command('list')
  .description('查看提醒配置')
  .action(() => {
    const list = reminders.getAllReminders();
    const rows = list.map(r => [
      r.id,
      r.type,
      r.enabled ? '✓' : '✗',
      r.schedule,
      r.message || '-'
    ]);
    console.log(renderTable(['ID', '类型', '启用', '时间', '消息'], rows));
    closeDatabase();
  });

reminderCmd
  .command('add <type> <schedule>')
  .description('添加提醒')
  .option('-m, --message <msg>', '提醒消息')
  .action((type, schedule, options) => {
    if (!['medication', 'bp_monitor', 'exercise'].includes(type)) {
      console.log(chalk.red('错误: 类型必须是 medication, bp_monitor 或 exercise'));
      return;
    }
    const id = reminders.addReminder({
      type: type as any,
      enabled: true,
      schedule,
      message: options.message
    });
    console.log(chalk.green(`✓ 提醒已添加 (ID: ${id})`));
    closeDatabase();
  });

reminderCmd
  .command('toggle <id>')
  .description('切换提醒状态')
  .action((id) => {
    const list = reminders.getAllReminders();
    const r = list.find(x => x.id === parseInt(id));
    if (!r) {
      console.log(chalk.red('错误: 提醒不存在'));
      return;
    }
    reminders.toggleReminder(parseInt(id), !r.enabled);
    console.log(chalk.green(`✓ 提醒已${r.enabled ? '禁用' : '启用'}`));
    closeDatabase();
  });

reminderCmd
  .command('init')
  .description('初始化默认提醒')
  .action(() => {
    initDefaultReminders();
    console.log(chalk.green('✓ 默认提醒已初始化'));
    closeDatabase();
  });

// ========== 综合命令 ==========
program
  .command('status')
  .description('查看健康状态概览')
  .action(() => {
    console.log(chalk.blue.bold('📊 健康状态概览'));
    console.log('');
    
    // 血压概览
    const bpSummary = bloodPressure.getBloodPressureSummary();
    console.log(chalk.cyan('🩺 血压记录'));
    console.log(`  总记录: ${bpSummary.total_records} 条`);
    if (bpSummary.latest_record) {
      console.log(`  最近记录: ${formatDate(bpSummary.latest_record)}`);
    }
    console.log('');
    
    // 运动概览
    const exSummary = exercise.getExerciseSummary();
    console.log(chalk.cyan('🏃 运动记录'));
    console.log(`  总记录: ${exSummary.total_records} 条`);
    console.log(`  总时长: ${exSummary.total_duration} 分钟`);
    console.log(`  总步数: ${exSummary.total_steps?.toLocaleString() || 0}`);
    console.log('');
    
    // 用药概览
    const medSummary = medication.getMedicationSummary();
    console.log(chalk.cyan('💊 用药记录'));
    console.log(`  总记录: ${medSummary.total_records} 条`);
    console.log(`  药物种类: ${medSummary.unique_medications} 种`);
    console.log('');
    
    // 今日数据
    console.log(chalk.cyan('📅 今日数据'));
    const todayMeds = medication.getTodayMedication();
    console.log(`  今日用药: ${todayMeds.length} 次`);
    
    closeDatabase();
  });

program.parse();
