---
name: health-manager
description: "Health data management system for tracking blood pressure, heart rate, exercise, and medication. Use when: (1) recording daily health metrics like blood pressure and heart rate, (2) tracking exercise activities and workouts, (3) managing medication schedules and reminders, (4) generating health reports and trend analysis, (5) monitoring health goals and progress. 适用场景：记录血压心率等健康指标、追踪运动锻炼、管理用药提醒、生成健康报告和趋势分析、监测健康目标。"
---

# Health Manager - 健康管理

综合健康数据管理系统，记录和分析血压、心率、运动等健康数据。

## 功能特性

### 1. 数据模型与存储
- SQLite 数据库存储
- 血压记录表（收缩压、舒张压、心率、时间、备注）
- 运动记录表（类型、时长、步数、消耗、时间）
- 用药记录表（药物、剂量、时间）
- 用户配置表
- 提醒配置表

### 2. 数据录入功能
- CLI 命令录入血压数据
- CLI 命令录入运动数据
- CLI 命令录入用药记录
- 批量导入（CSV/JSON格式）

### 3. 数据分析
- 血压趋势计算（7天/30天平均）
- 心率变化分析
- 运动统计（按类型、按日）
- 异常值检测

### 4. 智能提醒
- 用药提醒配置
- 血压监测提醒
- 运动提醒

### 5. 报告生成
- 日报生成
- 周报生成
- 健康手册生成（Markdown）

## 安装

```bash
cd ~/.openclaw/workspace/skills/health-manager
npm install
npm run build
```

## 使用方法

### 血压管理

```bash
# 添加血压记录
health bp add 120 80 --heart-rate 72 --notes "早晨测量"

# 查看血压记录
health bp list

# 查看血压趋势
health bp trend 7

# 查看异常血压
health bp abnormal
```

### 运动管理

```bash
# 添加运动记录
health ex add walking 30 --steps 5000 --calories 150

# 查看运动记录
health ex list

# 查看运动统计
health ex stats 7
```

### 用药管理

```bash
# 添加用药记录
health med add "降压药" "1片" --unit "片"

# 查看用药记录
health med list

# 查看今日用药
health med today
```

### 报告生成

```bash
# 生成日报
health report daily
health report daily 2024-01-15 --output report.md

# 生成周报
health report weekly
health report weekly --output weekly.md

# 生成健康手册
health report handbook --output handbook.md
```

### 数据导入导出

```bash
# 导出数据
health data export blood_pressure --format csv --output bp.csv
health data export-all ./backups

# 导入数据
health data import blood_pressure data.csv
health data import exercise data.json
```

### 配置管理

```bash
# 查看配置
health config list

# 设置配置项
health config set user.name "张三"

# 初始化用户配置
health config init --name "张三" --age 50 --height 170 --weight 70
```

### 提醒管理

```bash
# 查看提醒
health reminder list

# 初始化默认提醒
health reminder init

# 添加提醒
health reminder add medication "08:00" --message "该吃药了"

# 切换提醒状态
health reminder toggle 1
```

### 状态概览

```bash
health status
```

## 数据库位置

```bash
health data path
```

默认位置：`~/.config/health-manager/health.db`

## 技术栈

- Node.js / TypeScript
- SQLite (better-sqlite3)
- Commander.js (CLI)
- Chalk (终端颜色)

## 数据结构

### 血压记录
```typescript
{
  id: number;
  systolic: number;      // 收缩压
  diastolic: number;     // 舒张压
  heart_rate?: number;   // 心率
  recorded_at: string;   // 记录时间
  notes?: string;        // 备注
}
```

### 运动记录
```typescript
{
  id: number;
  type: string;          // 运动类型
  duration_minutes: number;  // 时长
  steps?: number;        // 步数
  calories_burned?: number;  // 消耗
  distance_km?: number;  // 距离
  recorded_at: string;
  notes?: string;
}
```

### 用药记录
```typescript
{
  id: number;
  name: string;          // 药物名称
  dosage: string;        // 剂量
  unit?: string;         // 单位
  taken_at: string;      // 服药时间
  notes?: string;
}
```

## 血压参考标准

| 分类 | 收缩压 (mmHg) | 舒张压 (mmHg) |
|------|-------------|-------------|
| 正常 | < 120 | < 80 |
| 正常偏高 | 120-129 | < 80 |
| 高血压前期 | 130-139 | 80-89 |
| 高血压 1 级 | 140-159 | 90-99 |
| 高血压 2 级 | ≥ 160 | ≥ 100 |
