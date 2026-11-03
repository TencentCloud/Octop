# Health Manager Skill 结构示例

## SKILL.md 内容示例

```markdown
# Health Manager Skill

一个综合健康数据管理系统，记录和分析用户的健康数据，生成个性化健康管理手册。

## 功能特性

### 数据接入
- Apple Health 数据导入
- 穿戴设备数据接入（手表、血压仪等）
- 手动数据录入

### 数据管理
- 血压监测记录
- 运动健康数据
- 用药记录
- 诊疗数据

### 智能分析
- 趋势分析
- 异常检测
- 数据关联分析

### 智能建议
- 用药提醒
- 运动建议
- 监测提醒
- 健康改善建议

### 输出
- 个人健康管理手册（PDF/Markdown）
- 趋势图表
- 日报/周报/月报

## 安装

```bash
clawhub install health-manager
```

## 使用方法

### 基本命令

```bash
# 记录血压
openclaw health record bp --systolic 120 --diastolic 80 --hr 75

# 记录运动
openclaw health record exercise --type walking --duration 30 --steps 5000

# 记录用药
openclaw health record medication --name "降压药" --dosage "10mg"

# 生成日报
openclaw health report daily

# 生成健康手册
openclaw health handbook

# 查看趋势
openclaw health trends --metric blood_pressure --period 30d
```

### 交互模式

```bash
openclaw health
```

进入交互式健康管理界面。

## 配置

在 `~/.openclaw/config/health-manager.json` 中配置：

```json
{
  "database": {
    "path": "~/.openclaw/data/health.db"
  },
  "reminders": {
    "enabled": true,
    "notification": true
  },
  "apple_health": {
    "enabled": false,
    "sync_interval": 3600
  },
  "export": {
    "default_format": "markdown",
    "save_path": "~/HealthReports"
  }
}
```

## 开发

### 项目结构

```
health-manager/
├── SKILL.md
├── package.json
├── src/
│   ├── index.js
│   ├── core/
│   ├── input/
│   ├── analysis/
│   ├── output/
│   └── cli/
├── templates/
├── config/
└── tests/
```

### 开发指南

1. 克隆仓库
2. 安装依赖：`npm install`
3. 开发测试：`npm test`
4. 构建发布：`npm run build`

## 许可证

MIT
```

## package.json 示例

```json
{
  "name": "@openclaw/health-manager",
  "version": "1.0.0",
  "description": "Comprehensive health data management system for OpenClaw",
  "main": "src/index.js",
  "scripts": {
    "start": "node src/index.js",
    "test": "jest",
    "build": "npm run lint && npm test",
    "lint": "eslint src/"
  },
  "keywords": [
    "health",
    "fitness",
    "medical",
    "tracking",
    "openclaw"
  ],
  "author": "OpenClaw Team",
  "license": "MIT",
  "dependencies": {
    "sqlite3": "^5.0.0",
    "moment": "^2.29.0",
    "chart.js": "^3.0.0",
    "puppeteer": "^13.0.0",
    "healthkit": "^2.0.0",
    "bull": "^4.0.0"
  },
  "devDependencies": {
    "jest": "^27.0.0",
    "eslint": "^8.0.0"
  },
  "openclaw": {
    "skill": true,
    "commands": [
      "health"
    ],
    "config_schema": "config/schema.json"
  }
}
```

## 配置文件示例

### config/default.json
```json
{
  "database": {
    "client": "sqlite3",
    "connection": {
      "filename": "~/.openclaw/data/health.db"
    }
  },
  "reminders": {
    "check_interval": 300000,
    "notification_sound": true
  },
  "analysis": {
    "trend_window_days": 30,
    "anomaly_threshold": 2.5
  },
  "export": {
    "formats": ["markdown", "pdf", "html"],
    "auto_save": true
  }
}
```

## 测试文件示例

### tests/health-manager.test.js
```javascript
const HealthManager = require('../src/index');

describe('Health Manager', () => {
  let hm;

  beforeEach(() => {
    hm = new HealthManager();
  });

  test('should record blood pressure', () => {
    const record = hm.recordBloodPressure({
      systolic: 120,
      diastolic: 80,
      heartRate: 75
    });
    expect(record.id).toBeDefined();
    expect(record.systolic).toBe(120);
  });

  test('should generate daily report', async () => {
    const report = await hm.generateDailyReport('2026-03-09');
    expect(report).toHaveProperty('summary');
    expect(report).toHaveProperty('charts');
  });

  test('should detect anomalies', () => {
    const anomalies = hm.detectAnomalies('blood_pressure', 7);
    expect(Array.isArray(anomalies)).toBe(true);
  });
});
```

## 模板文件示例

### templates/handbook.md
```markdown
# 个人健康管理手册

## 基本信息
- **姓名**: {{user.name}}
- **年龄**: {{user.age}}
- **身高**: {{user.height}} cm
- **体重**: {{user.weight}} kg
- **BMI**: {{user.bmi}}

## 健康数据概览

### 血压趋势
{{blood_pressure_chart}}

### 运动统计
{{exercise_summary}}

### 用药记录
{{medication_history}}

## 健康建议

### 近期建议
{{recent_recommendations}}

### 长期目标
{{long_term_goals}}

## 紧急联系信息
{{emergency_contacts}}

---
*本手册生成时间: {{generated_at}}*
*数据截止时间: {{data_until}}*
```

## CLI 命令示例

### src/cli/commands.js
```javascript
const { Command } = require('commander');
const HealthManager = require('../core/manager');

const program = new Command();

program
  .name('health')
  .description('Health data management system')
  .version('1.0.0');

program
  .command('record')
  .description('Record health data')
  .addCommand(recordBloodPressure())
  .addCommand(recordExercise())
  .addCommand(recordMedication());

function recordBloodPressure() {
  const cmd = new Command('bp')
    .description('Record blood pressure')
    .requiredOption('-s, --systolic <number>', 'Systolic pressure')
    .requiredOption('-d, --diastolic <number>', 'Diastolic pressure')
    .option('-h, --heart-rate <number>', 'Heart rate')
    .action((options) => {
      const hm = new HealthManager();
      hm.recordBloodPressure(options);
      console.log('Blood pressure recorded successfully');
    });
  return cmd;
}

// 更多命令定义...
```

## 部署说明

### 本地部署
```bash
# 安装
npm install -g @openclaw/health-manager

# 初始化
openclaw health init

# 启动服务
openclaw health start
```

### Docker部署
```dockerfile
FROM node:16-alpine

WORKDIR /app
COPY package*.json ./
RUN npm install --production
COPY . .

EXPOSE 3000
CMD ["node", "src/index.js"]
```

---

这个示例展示了 Health Manager Skill 的基本结构和实现要点。实际开发时可以根据需求调整和扩展。