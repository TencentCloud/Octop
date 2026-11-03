# Health Manager

> 智能健康数据管理助手，让健康管理更简单

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](https://github.com/your-repo/health-manager)

---

## 项目简介

**Health Manager** 是一个命令行健康数据管理工具，帮助你轻松记录、分析和理解自己的健康数据。无论是血压监测、心率跟踪，还是运动记录和用药管理，Health Manager 都能提供简洁高效的管理体验。

### ✨ 核心价值

- **简化记录** - 一条命令完成数据录入，支持简写和快捷方式
- **智能分析** - 自动生成趋势分析，识别健康模式
- **个性化报告** - 生成专属健康手册，方便与医生分享
- **贴心提醒** - 用药、监测、运动提醒，养成健康习惯

---

## 功能特性

### 📊 健康数据记录

| 数据类型 | 支持字段 | 快捷命令 |
|---------|---------|---------|
| 血压 | 收缩压、舒张压、脉搏、体位、手臂 | `health-manager record bp` |
| 心率 | 心率值、活动状态、设备来源 | `health-manager record hr` |
| 运动 | 类型、时长、距离、卡路里、心率 | `health-manager record ex` |
| 用药 | 药品名称、剂量、服药时间、备注 | `health-manager record med` |

### 📈 趋势分析

- **可视化图表** - 血压、心率、运动趋势一目了然
- **智能识别** - 自动识别异常数据和健康模式
- **对比分析** - 周期对比，了解健康变化趋势
- **目标追踪** - 对照个人健康目标，追踪完成情况

### ⏰ 智能提醒

- **用药提醒** - 定时提醒服药，支持多次和周期设置
- **监测提醒** - 血压、心率测量提醒
- **运动提醒** - 运动计划提醒，养成运动习惯
- **异常预警** - 数据异常时主动提醒

### 📖 健康手册

- **月度报告** - 汇总当月数据，分析健康状态
- **季度总结** - 更长周期的趋势分析
- **年度总览** - 全年健康数据全景展示
- **多种格式** - 支持 PDF、HTML、Markdown 输出

---

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-repo/health-manager.git
cd health-manager

# 安装依赖
npm install

# 全局链接（可选）
npm link
```

### 初始化

```bash
# 初始化配置
health-manager init

# 设置个人信息
health-manager config set user.name "张三"
health-manager config set user.age 45
```

### 第一次记录

```bash
# 记录血压
health-manager record bp -s 120 -d 80 -p 72

# 记录心率
health-manager record hr --rate 68

# 记录运动
health-manager record ex --type running --duration 30

# 记录用药
health-manager record med --name "降压药" --dosage "1片"
```

### 查看数据

```bash
# 查看最近7天记录
health-manager list --recent 7

# 分析血压趋势
health-manager analyze bp --period 30d

# 生成健康手册
health-manager handbook --period month
```

---

## 技术栈

### 核心技术

- **运行时**: Node.js 18+
- **语言**: TypeScript 5.0+
- **CLI框架**: Commander.js
- **数据处理**: Lodash, Date-fns
- **图表生成**: Chart.js, QuickChart
- **PDF生成**: Puppeteer, PDFKit

### 数据存储

- **本地存储**: JSON 文件
- **数据导入**: XML (Apple Health), CSV
- **数据导出**: JSON, CSV, PDF, HTML

### 集成支持

- **Apple Health**: XML 导入，自动同步
- **Google Fit**: OAuth 认证，数据同步
- **可穿戴设备**: 支持 Apple Watch、小米手环等数据导入

---

## 使用示例

### 场景一：日常血压监测

```bash
# 早晨测量后记录
health-manager record bp -s 118 -d 78 -p 70 --notes "晨起测量"

# 晚上测量后记录
health-manager record bp -s 125 -d 82 -p 75 --notes "睡前测量"

# 查看一周趋势
health-manager analyze bp --period 7d --chart

# 生成月度血压报告
health-manager handbook bp --period month
```

### 场景二：运动记录

```bash
# 记录晨跑
health-manager record ex \
  --type running \
  --duration 30 \
  --distance 5.2 \
  --calories 280

# 记录游泳
health-manager record ex \
  --type swimming \
  --duration 45 \
  --calories 350

# 查看本月运动统计
health-manager analyze ex --period month

# 查看运动目标完成情况
health-manager report exercise --goals
```

### 场景三：用药管理

```bash
# 添加每日用药提醒
health-manager remind add med \
  --name "降压药" \
  --time "08:00,20:00"

# 记录服药
health-manager record med --name "降压药" --taken

# 查看用药记录
health-manager list med --month

# 用药提醒状态
health-manager remind list
```

### 场景四：健康报告生成

```bash
# 生成月度健康手册
health-manager handbook --period month --output ~/健康手册.pdf

# 生成季度报告（HTML格式）
health-manager handbook --period quarter --format html

# 生成包含所有数据的年度总结
health-manager handbook --period year --include all
```

---

## 目录结构

```
health-manager/
├── bin/
│   └── health-manager        # CLI 入口
├── src/
│   ├── commands/            # 命令实现
│   │   ├── record.ts        # 记录命令
│   │   ├── list.ts          # 查询命令
│   │   ├── analyze.ts       # 分析命令
│   │   ├── handbook.ts      # 手册生成
│   │   └── remind.ts        # 提醒管理
│   ├── models/              # 数据模型
│   │   ├── blood-pressure.ts
│   │   ├── heart-rate.ts
│   │   ├── exercise.ts
│   │   └── medication.ts
│   ├── services/            # 业务逻辑
│   │   ├── data-service.ts
│   │   ├── analysis-service.ts
│   │   ├── chart-service.ts
│   │   └── notification-service.ts
│   ├── utils/               # 工具函数
│   └── config/               # 配置管理
├── templates/               # 手册模板
│   ├── handbook-pdf.hbs
│   └── handbook-html.hbs
├── tests/                   # 测试文件
├── docs/                    # 文档
│   ├── USER_GUIDE.md
│   └── API.md
├── package.json
├── tsconfig.json
└── README.md
```

---

## 开发指南

### 环境准备

```bash
# 安装开发依赖
npm install

# 运行测试
npm test

# 代码检查
npm run lint

# 构建
npm run build
```

### 添加新命令

1. 在 `src/commands/` 创建命令文件
2. 在 `bin/health-manager` 注册命令
3. 添加对应的数据模型和服务
4. 编写测试用例

### 数据格式规范

所有健康数据遵循统一的 JSON Schema，详见 [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md)

---

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

---

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 致谢

感谢以下开源项目：

- [Commander.js](https://github.com/tj/commander.js) - CLI 框架
- [Chart.js](https://www.chartjs.org/) - 图表库
- [Date-fns](https://date-fns.org/) - 日期处理
- [Puppeteer](https://pptr.dev/) - PDF 生成

---

## 联系方式

- 项目主页: https://github.com/your-repo/health-manager
- 问题反馈: https://github.com/your-repo/health-manager/issues
- 邮箱: health-manager@example.com