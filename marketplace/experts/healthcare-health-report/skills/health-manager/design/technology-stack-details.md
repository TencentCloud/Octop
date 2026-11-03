# 技术选型详细说明

## 1. 数据库技术选型

### 1.1 SQLite
**选择理由：**
- 零配置，适合本地应用
- 单个文件存储，便于备份和迁移
- ACID 事务支持
- 成熟的 Node.js 驱动 (better-sqlite3, sqlite3)

**性能考量：**
- 适合中小规模数据量（< 10GB）
- 并发读取性能优秀，写入需注意锁争用
- 支持 JSON1 和 FTS5 扩展

**健康数据适用性：**
- 用户个人健康数据量可控
- 无需分布式部署
- 隐私数据本地存储更安全

**配置示例：**
```javascript
const Database = require('better-sqlite3');
const db = new Database('~/.openclaw/data/health.db');

// 启用性能优化
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');
db.pragma('cache_size = -2000'); // 2GB cache
```

### 1.2 时序数据存储方案
**备选方案：**

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| SQLite + 分区表 | 简单，无需额外服务 | 查询优化需手动设计 | 个人使用，数据量小 |
| TimescaleDB | 专业时序数据库，性能优秀 | 需要 PostgreSQL 服务 | 数据量大，需要复杂分析 |
| InfluxDB | 专门为时序数据设计 | 学习曲线，资源消耗 | 高频数据采集 |
| QuestDB | 高性能，SQL兼容 | 相对较新，社区较小 | 大规模数据实时分析 |

**推荐方案：**
- **初期**: SQLite 分区表（按年月分区）
- **中期**: TimescaleDB（数据量 > 1千万条）
- **云部署**: 可考虑 InfluxDB Cloud

### 1.3 缓存层 - Redis
**使用场景：**
1. 频繁查询的结果缓存（趋势数据、用户画像）
2. 任务队列存储（Bull 库依赖）
3. 会话管理（Web界面）
4. 实时通知推送

**配置建议：**
```javascript
const Redis = require('ioredis');
const redis = new Redis({
  host: 'localhost',
  port: 6379,
  password: process.env.REDIS_PASSWORD,
  db: 0, // 健康数据专用
  keyPrefix: 'health:'
});

// 缓存策略
const CACHE_TTL = {
  DAILY_SUMMARY: 3600, // 1小时
  TREND_DATA: 1800,    // 30分钟
  USER_PROFILE: 86400, // 24小时
};
```

## 2. 数据处理和分析技术

### 2.1 数据分析库选型

**Node.js 选项：**

| 库 | 特点 | 适用场景 |
|----|------|----------|
| Danfo.js | pandas 风格的 DataFrame | 数据清洗、转换、分析 |
| Simple-statistics | 基础统计函数 | 简单统计计算 |
| ML5.js | 机器学习库 | 异常检测、预测 |
| TensorFlow.js | 深度学习 | 复杂模式识别 |

**Python 集成方案（如需要）：**
```javascript
// 使用 child_process 调用 Python 脚本
const { spawn } = require('child_process');

function analyzeWithPython(data) {
  return new Promise((resolve, reject) => {
    const python = spawn('python3', ['-c', pythonScript]);
    // 数据通过 stdin 传递，结果通过 stdout 返回
  });
}
```

**推荐方案：**
- **基础分析**: Danfo.js + Simple-statistics
- **高级ML**: TensorFlow.js（预训练模型）
- **复杂分析**: Python 微服务（pandas + scikit-learn）

### 2.2 图表生成

**服务器端图表生成：**
- **Chart.js + node-canvas**: 成熟方案，支持多种图表类型
- **D3.js + JSDOM**: 灵活但较重
- **QuickChart**: 在线服务，简单但依赖网络

**推荐方案：**
```javascript
const { createCanvas } = require('canvas');
const { Chart } = require('chart.js');

function generateChart(data, options) {
  const canvas = createCanvas(800, 400);
  const ctx = canvas.getContext('2d');
  
  new Chart(ctx, {
    type: 'line',
    data: data,
    options: options
  });
  
  return canvas.toBuffer();
}
```

## 3. 健康数据接入技术

### 3.1 Apple Health 集成

**技术方案：**
1. **HealthKit JS（iOS App）**: 需要 iOS 应用封装
2. **Health Export + 解析**: 用户导出 XML，系统解析
3. **第三方服务**: 如 Apple Health 数据中转服务

**推荐方案：**
- **Mac 用户**: 使用 `@kingstinct/react-native-health` 的 Node.js 适配
- **通用方案**: 指导用户导出 Health Data，解析 XML

**数据解析示例：**
```javascript
const parseHealthExport = (xmlContent) => {
  // 解析 Apple Health 导出的 export.xml
  // 提取血压、心率、步数等数据
  // 转换为统一格式
};
```

### 3.2 穿戴设备接入

**蓝牙/BLE 设备：**
- **血压计**: 使用 `noble` 库连接蓝牙设备
- **智能手表**: 通过厂商 SDK 或反向工程

**厂商API集成：**
- **华为运动健康**: REST API
- **小米运动**: 需要模拟登录和抓包
- **Fitbit/Google Fit**: 官方 API

**设备连接架构：**
```javascript
class WearableManager {
  constructor() {
    this.ble = require('noble');
    this.connectedDevices = new Map();
  }
  
  async connectBloodPressureMonitor() {
    // 扫描特定 UUID 的设备
    // 建立连接
    // 订阅数据通知
    // 解析数据包
  }
}
```

## 4. 任务调度和队列

### 4.1 Bull 任务队列

**队列设计：**
```javascript
const Queue = require('bull');

const queues = {
  dataSync: new Queue('data-sync', {
    redis: { port: 6379, host: 'localhost' }
  }),
  analysis: new Queue('analysis', {
    limiter: { max: 1, duration: 1000 } // 限流：1秒1个任务
  }),
  report: new Queue('report-generation'),
  reminder: new Queue('reminder-check')
};

// 定义任务处理器
queues.dataSync.process('apple-health', async (job) => {
  // Apple Health 同步逻辑
});

queues.analysis.process('trend', async (job) => {
  // 趋势分析逻辑
});
```

### 4.2 定时任务调度

**方案比较：**
- **node-cron**: 简单，适合基础调度
- **bull + 重复任务**: 更可靠，支持重试和监控
- **PM2 定时任务**: 依赖 PM2，适合生产环境

**推荐方案：**
```javascript
const cron = require('node-cron');
const Bull = require('bull');

// 简单任务用 node-cron
cron.schedule('0 8 * * *', () => {
  // 每天8点生成日报
  queues.report.add('daily', { date: new Date() });
});

// 复杂任务用 Bull 重复任务
queues.reminder.add(
  'check-due-reminders',
  {},
  { repeat: { cron: '*/5 * * * *' } } // 每5分钟检查一次
);
```

## 5. 报告生成技术

### 5.1 PDF 生成方案

**选项比较：**

| 方案 | 优点 | 缺点 |
|------|------|------|
| Puppeteer | 高质量，支持复杂样式 | 资源消耗大，需要 Chrome |
| PDFKit | 轻量，纯 JS | 样式控制复杂 |
| jsPDF + html2canvas | 客户端友好 | 服务器端兼容性问题 |
| WeasyPrint | 高质量 CSS 渲染 | 需要 Python 环境 |

**推荐方案：Puppeteer**
```javascript
const puppeteer = require('puppeteer');

async function generatePDF(htmlContent, outputPath) {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const page = await browser.newPage();
  await page.setContent(htmlContent, { waitUntil: 'networkidle0' });
  
  await page.pdf({
    path: outputPath,
    format: 'A4',
    margin: { top: '2cm', right: '2cm', bottom: '2cm', left: '2cm' },
    printBackground: true
  });
  
  await browser.close();
}
```

### 5.2 模板引擎

**选项：**
- **Handlebars**: 简单，逻辑少
- **EJS**: 嵌入 JavaScript 逻辑
- **Nunjucks**: 功能丰富，类似 Jinja2
- **Markdown + 变量替换**: 最简单

**推荐方案：Handlebars + 自定义 Helper**
```javascript
const handlebars = require('handlebars');
const fs = require('fs').promises;

// 注册健康数据专用 helper
handlebars.registerHelper('formatBloodPressure', function(systolic, diastolic) {
  return `${systolic}/${diastolic} mmHg`;
});

handlebars.registerHelper('trendIcon', function(trend) {
  const icons = { up: '↗️', down: '↘️', stable: '→' };
  return icons[trend] || '➡️';
});

async function renderTemplate(templateName, data) {
  const templateContent = await fs.readFile(
    `templates/${templateName}.hbs`,
    'utf-8'
  );
  const template = handlebars.compile(templateContent);
  return template(data);
}
```

## 6. 安全和隐私技术

### 6.1 数据加密

**存储加密：**
```javascript
const crypto = require('crypto');

class HealthDataEncryptor {
  constructor(masterKey) {
    this.algorithm = 'aes-256-gcm';
    this.key = crypto.scryptSync(masterKey, 'salt', 32);
  }
  
  encrypt(text) {
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipheriv(this.algorithm, this.key, iv);
    const encrypted = Buffer.concat([cipher.update(text, 'utf8'), cipher.final()]);
    const authTag = cipher.getAuthTag();
    
    return {
      iv: iv.toString('hex'),
      content: encrypted.toString('hex'),
      tag: authTag.toString('hex')
    };
  }
  
  decrypt(encryptedData) {
    // 解密逻辑
  }
}
```

### 6.2 匿名化处理

**数据脱敏：**
```javascript
function anonymizeHealthData(data) {
  return {
    ...data,
    // 移除直接标识符
    userId: hashUserId(data.userId),
    // 泛化敏感信息
    age: Math.floor(data.age / 10) * 10, // 10岁区间
    location: generalizeLocation(data.location),
    // 添加噪声
    systolic: addNoise(data.systolic, 2), // ±2mmHg 噪声
    // 保留医疗价值，去除身份信息
  };
}
```

## 7. 监控和运维

### 7.1 健康检查

```javascript
const healthCheck = {
  database: async () => {
    try {
      await db.pragma('integrity_check');
      return { status: 'healthy' };
    } catch (error) {
      return { status: 'unhealthy', error: error.message };
    }
  },
  
  redis: async () => {
    try {
      await redis.ping();
      return { status: 'healthy' };
    } catch (error) {
      return { status: 'unhealthy', error: error.message };
    }
  },
  
  diskSpace: () => {
    const freeBytes = require('check-disk-space').sync('/').free;
    const freeGB = freeBytes / 1024 / 1024 / 1024;
    return {
      status: freeGB > 1 ? 'healthy' : 'warning',
      free: `${freeGB.toFixed(2)} GB`
    };
  }
};
```

### 7.2 日志系统

**结构化日志：**
```javascript
const winston = require('winston');

const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.File({ 
      filename: 'logs/health-manager-error.log', 
      level: 'error' 
    }),
    new winston.transports.File({ 
      filename: 'logs/health-manager-combined.log' 
    }),
    new winston.transports.Console({
      format: winston.format.simple()
    })
  ]
});

// 健康数据专用日志上下文
logger.health = (action, data) => {
  logger.info('HEALTH_ACTION', { 
    action, 
    userId: data.userId,
    timestamp: new Date().toISOString(),
    // 不记录敏感健康数据
  });
};
```

## 8. 测试策略

### 8.1 测试金字塔

```javascript
// 单元测试 (Jest)
describe('BloodPressureValidator', () => {
  test('validates normal range', () => {
    expect(validateBloodPressure(120, 80)).toBe(true);
    expect(validateBloodPressure(300, 200)).toBe(false);
  });
});

// 集成测试
describe('HealthDataIntegration', () => {
  test('full data pipeline', async () => {
    const record = await recordBloodPressure(testData);
    const analysis = await analyzeTrends([record]);
    const report = await generateReport(analysis);
    expect(report).toHaveProperty('summary');
  });
});

// E2E 测试 (Puppeteer)
describe('WebInterface', () => {
  test('user can record and view data', async () => {
    const browser = await puppeteer.launch();
    const page = await browser.newPage();
    // 模拟用户操作
    await page.click('#record-bp');
    await page.type('#systolic', '120');
    // 验证结果
  });
});
```

## 9. 部署架构

### 9.1 本地部署（推荐）

```
用户设备
├── OpenClaw Core
├── Health Manager Skill
│   ├── Node.js 进程
│   ├── SQLite 数据库
│   └── Redis 缓存
└── 数据目录 (~/.openclaw/data/health/)
```

### 9.2 云部署（可选）

```
Docker 容器
├── 应用层 (Node.js + Express)
├── 数据层 (PostgreSQL + TimescaleDB)
├── 缓存层 (Redis)
├── 文件存储 (S3/MinIO)
└── 监控层 (Prometheus + Grafana)
```

### 9.3 混合部署

```
本地设备 (隐私数据)
├── 原始健康数据存储
├── 实时分析
└── 本地提醒

云端服务 (匿名分析)
├── 聚合统计
├── 机器学习模型训练
└── 社区基准对比
```

---

**技术选型总结：**

1. **核心**: Node.js + SQLite + Redis
2. **数据处理**: Danfo.js + 自定义算法
3. **可视化**: Chart.js + Puppeteer
4. **任务调度**: Bull + node-cron
5. **设备接入**: 厂商API + 蓝牙库
6. **安全**: 本地加密 + 匿名化

这个技术栈平衡了功能需求、开发效率和运行性能，特别适合作为 OpenClaw Skill 实现。