# 健康管理 Skill 架构设计

## 1. 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenClaw Skill Layer                    │
├─────────────────────────────────────────────────────────────┤
│                    Health Manager Skill                      │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐  │
│  │  数据接入层  │  │  数据处理层  │  │    智能分析层     │  │
│  │ Data Input  │  │   Data     │  │   Analytics      │  │
│  │   Layer     │  │ Processing │  │     Layer        │  │
│  └─────────────┘  └─────────────┘  └───────────────────┘  │
│         │                  │                    │          │
│         ▼                  ▼                    ▼          │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐  │
│  │ Apple Health│  │  数据存储    │  │  趋势分析引擎     │  │
│  │ Wearables   │  │  Data Store │  │  Trend Analysis  │  │
│  │ Manual Entry│  │             │  │  异常检测        │  │
│  └─────────────┘  └─────────────┘  │  关联分析        │  │
│                                     └───────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    Output Layer                             │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐  │
│  │ 健康手册生成 │  │  图表生成    │  │  报告生成系统     │  │
│  │ Handbook    │  │  Chart      │  │  Reporting       │  │
│  │ Generator   │  │ Generator   │  │  System          │  │
│  └─────────────┘  └─────────────┘  └───────────────────┘  │
│         │                  │                    │          │
│         ▼                  ▼                    ▼          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                 输出格式 (PDF/Markdown)                │  │
│  │               Charts (PNG/SVG)                        │  │
│  │               Reports (Daily/Weekly/Monthly)          │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 架构说明

1. **数据接入层**:
   - Apple Health 集成：通过 HealthKit API 读取健康数据
   - 穿戴设备接入：支持蓝牙/BLE 设备连接（血压仪、心率带等）
   - 手动录入：提供命令行和Web界面输入表单

2. **数据处理层**:
   - 数据清洗和标准化
   - 数据存储（SQLite + 时间序列数据库）
   - 数据索引和查询优化

3. **智能分析层**:
   - 趋势分析：使用统计方法分析血压、心率等指标的变化趋势
   - 异常检测：基于阈值和机器学习算法识别异常数据
   - 关联分析：分析用药、运动与健康指标的相关性

4. **输出层**:
   - 健康手册生成：整合所有数据和分析结果生成个性化手册
   - 图表生成：可视化趋势和统计数据
   - 报告系统：自动生成日报、周报、月报

## 2. 数据模型设计

### 2.1 核心实体

```yaml
# 用户信息
User:
  - id: string (UUID)
  - name: string
  - age: integer
  - gender: string (male/female/other)
  - height: float (cm)
  - weight: float (kg)
  - created_at: timestamp
  - updated_at: timestamp

# 血压记录
BloodPressureRecord:
  - id: string (UUID)
  - user_id: string (外键)
  - systolic: integer (收缩压, mmHg)
  - diastolic: integer (舒张压, mmHg)
  - heart_rate: integer (心率, bpm)
  - measurement_time: timestamp
  - notes: text (备注)
  - source: string (manual/apple_health/wearable)
  - device_id: string (设备标识)
  - created_at: timestamp

# 运动记录
ExerciseRecord:
  - id: string (UUID)
  - user_id: string
  - exercise_type: string (walking/running/cycling/swimming/etc.)
  - duration: integer (分钟)
  - distance: float (公里)
  - calories: integer (卡路里)
  - start_time: timestamp
  - end_time: timestamp
  - heart_rate_avg: integer (平均心率)
  - heart_rate_max: integer (最大心率)
  - steps: integer (步数, 仅步行/跑步)
  - source: string (manual/apple_health/wearable)
  - created_at: timestamp

# 用药记录
MedicationRecord:
  - id: string (UUID)
  - user_id: string
  - medication_name: string (药物名称)
  - dosage: string (剂量, e.g., "10mg")
  - frequency: string (频率, e.g., "每日两次")
  - taken_time: timestamp (服药时间)
  - notes: text (备注)
  - status: string (taken/missed/skipped)
  - created_at: timestamp

# 诊疗记录
MedicalRecord:
  - id: string (UUID)
  - user_id: string
  - record_type: string (diagnosis/treatment/lab_result)
  - title: string (标题)
  - description: text (详细描述)
  - date: timestamp
  - doctor: string (医生姓名)
  - hospital: string (医院)
  - attachments: array (附件路径)
  - created_at: timestamp

# 健康目标
HealthGoal:
  - id: string (UUID)
  - user_id: string
  - goal_type: string (blood_pressure/weight/exercise/medication)
  - target_value: string (目标值)
  - current_value: string (当前值)
  - start_date: timestamp
  - end_date: timestamp
  - status: string (active/completed/failed)
  - created_at: timestamp

# 提醒设置
Reminder:
  - id: string (UUID)
  - user_id: string
  - reminder_type: string (medication/exercise/measurement)
  - title: string
  - message: string
  - schedule: json (cron表达式或时间规则)
  - enabled: boolean
  - last_triggered: timestamp
  - created_at: timestamp
```

### 2.2 数据库设计

- **主存储**: SQLite (本地，适合个人健康数据)
- **时间序列数据**: 考虑使用 TimescaleDB (PostgreSQL扩展) 或专门的时序数据库
- **缓存层**: Redis (用于频繁查询的数据缓存)
- **文件存储**: 本地文件系统 (PDF报告、图表图片)

### 2.3 数据关系

```
User 1:n BloodPressureRecord
User 1:n ExerciseRecord
User 1:n MedicationRecord
User 1:n MedicalRecord
User 1:n HealthGoal
User 1:n Reminder

BloodPressureRecord → 可关联 MedicationRecord (用药效果分析)
ExerciseRecord → 可关联 BloodPressureRecord (运动影响分析)
```

## 3. 核心交互流程

### 3.1 数据收集流程

```
1. 用户启动数据收集
   ├─ 自动收集: Apple Health 同步 (定时任务)
   ├─ 设备连接: 蓝牙血压仪/手表数据读取
   └─ 手动录入: 命令行输入或Web表单

2. 数据验证和清洗
   ├─ 范围检查 (血压值是否在合理范围)
   ├─ 异常值检测
   └─ 数据标准化 (单位转换)

3. 数据存储
   └─ 写入数据库并建立索引

4. 触发分析
   └─ 有新数据时自动触发分析任务
```

### 3.2 分析流程

```
1. 数据准备
   ├─ 查询相关时间段数据
   ├─ 数据聚合 (按天/周/月)
   └─ 数据预处理

2. 趋势分析
   ├─ 计算移动平均
   ├─ 识别趋势方向 (上升/下降/平稳)
   └─ 生成趋势报告

3. 异常检测
   ├─ 阈值检测 (超过预设阈值)
   ├─ 统计异常检测 (3σ原则)
   └─ 模式异常检测 (与历史模式比较)

4. 关联分析
   ├─ 用药与血压关联
   ├─ 运动与心率关联
   └─ 时间与健康指标关联

5. 生成建议
   └─ 基于分析结果生成个性化建议
```

### 3.3 报告生成流程

```
1. 用户请求报告
   ├─ 选择报告类型 (日报/周报/月报/健康手册)
   ├─ 选择时间范围
   └─ 选择输出格式 (PDF/Markdown)

2. 数据收集
   ├─ 获取健康数据
   ├─ 获取分析结果
   └─ 获取建议内容

3. 报告生成
   ├─ 模板渲染
   ├─ 图表生成
   └─ 格式转换

4. 输出交付
   └─ 保存文件/发送通知/预览显示
```

## 4. 技术选型建议

### 4.1 后端技术栈

1. **核心运行时**: Node.js (与 OpenClaw 生态兼容)
2. **数据库**:
   - SQLite (主数据库，轻量级，无需额外服务)
   - Redis (缓存和会话管理)
3. **数据处理**:
   - Pandas (Python) 或 Danfo.js (Node.js) 用于数据分析
   - TensorFlow.js 或 ONNX Runtime 用于机器学习模型
4. **任务队列**: Bull (基于 Redis 的任务队列)
5. **API 框架**: Express 或 Fastify
6. **数据可视化**:
   - Chart.js 或 D3.js 用于图表生成
   - Puppeteer 用于 PDF 生成
7. **健康数据接入**:
   - Apple Health: `healthkit` npm 包
   - 蓝牙设备: `noble` 或 `bleno` 库

### 4.2 前端技术栈 (如需Web界面)

1. **框架**: React 或 Vue.js
2. **UI 组件库**: Ant Design 或 Material-UI
3. **图表库**: Recharts 或 Victory
4. **移动端**: React Native (如需移动应用)

### 4.3 部署架构

```
本地部署 (推荐):
  - OpenClaw 作为主运行环境
  - Skill 作为插件安装
  - 所有数据存储在本地，保证隐私安全

云部署 (可选):
  - Docker 容器化
  - 数据加密存储
  - 定期备份机制
```

### 4.4 第三方服务集成

1. **Apple Health**: 通过 HealthKit REST API
2. **Google Fit**: 通过 Google Fit API
3. **穿戴设备厂商 API**: 如华为健康、小米运动等
4. **天气数据**: 用于分析天气对健康的影响
5. **日历集成**: 用于分析日程与健康关系

## 5. UI/UX 设计建议

### 5.1 设计原则

1. **隐私优先**: 明确显示数据存储位置，提供数据导出和删除功能
2. **简洁直观**: 健康数据复杂，但界面应简单易懂
3. **个性化**: 根据用户健康目标和偏好定制界面
4. **及时反馈**: 数据录入后立即显示分析结果
5. **可访问性**: 支持大字体、高对比度等辅助功能

### 5.2 核心界面设计

#### 5.2.1 仪表盘 (Dashboard)
- 今日健康概览 (血压、步数、心率)
- 关键指标趋势图
- 待办提醒 (用药、测量)
- 快速录入按钮

#### 5.2.2 数据录入界面
- 表单式录入 (血压、运动、用药)
- 语音录入支持
- 批量导入功能
- 拍照识别 (药品说明书)

#### 5.2.3 数据分析界面
- 可交互的时间轴图表
- 多指标对比视图
- 关联分析可视化
- 异常点高亮显示

#### 5.2.4 报告查看界面
- 报告列表 (按时间排序)
- 预览功能
- 导出选项 (PDF/Markdown/图片)
- 分享功能 (加密链接)

#### 5.2.5 设置界面
- 数据源管理 (Apple Health/设备连接)
- 提醒设置
- 健康目标设定
- 隐私和数据管理

### 5.3 交互设计细节

1. **数据可视化**:
   - 使用颜色编码: 绿色=正常，黄色=注意，红色=异常
   - 提供图例和说明
   - 支持图表缩放和细节查看

2. **提醒系统**:
   - 多种提醒方式: 通知、声音、震动
   - 智能推迟功能
   - 确认反馈 (已服药/已测量)

3. **多端同步**:
   - 手机端: 快速录入和查看
   - 桌面端: 详细分析和报告生成
   - 手表端: 快捷操作和即时查看

### 5.4 无障碍设计

- 支持屏幕阅读器
- 键盘导航支持
- 高对比度模式
- 字体大小调整
- 语音控制支持

## 6. Skill 实现规划

### 6.1 开发阶段

**阶段1: MVP (最小可行产品)**
- 基础数据模型和存储
- 手动数据录入
- 简单趋势分析
- 基础报告生成 (Markdown格式)

**阶段2: 数据接入扩展**
- Apple Health 集成
- 文件导入导出
- 增强分析功能
- PDF 报告生成

**阶段3: 智能功能**
- 异常检测算法
- 个性化建议引擎
- 提醒系统
- 多用户支持

**阶段4: 高级功能**
- 机器学习预测
- 穿戴设备集成
- 健康风险评估
- 社区分享功能

### 6.2 Skill 目录结构

```
health-manager/
├── SKILL.md                    # Skill 描述文档
├── package.json               # Node.js 依赖
├── src/
│   ├── index.js              # 主入口文件
│   ├── core/
│   │   ├── database.js       # 数据库连接
│   │   ├── models.js         # 数据模型
│   │   └── validation.js     # 数据验证
│   ├── input/
│   │   ├── manual.js         # 手动录入
│   │   ├── apple-health.js   # Apple Health 集成
│   │   └── wearable.js       # 穿戴设备接入
│   ├── analysis/
│   │   ├── trends.js         # 趋势分析
│   │   ├── anomalies.js      # 异常检测
│   │   └── correlations.js   # 关联分析
│   ├── output/
│   │   ├── handbook.js       # 健康手册生成
│   │   ├── charts.js         # 图表生成
│   │   └── reports.js        # 报告生成
│   ├── utils/
│   │   ├── date.js           # 日期工具
│   │   └── formatters.js     # 格式化工具
│   └── cli/
│       ├── commands.js       # CLI 命令定义
│       └── prompts.js        # 交互式提示
├── templates/
│   ├── handbook.md           # 健康手册模板
│   └── report.md             # 报告模板
├── config/
│   └── default.json          # 默认配置
└── tests/                    # 测试文件
```

### 6.3 关键API设计

```javascript
// 数据录入 API
healthManager.record.bloodPressure({ systolic, diastolic, heartRate, timestamp })
healthManager.record.exercise({ type, duration, distance, calories })
healthManager.record.medication({ name, dosage, time })

// 数据分析 API
healthManager.analyze.trends({ metric, period }) // 趋势分析
healthManager.analyze.anomalies({ metric, threshold }) // 异常检测
healthManager.analyze.correlations({ metric1, metric2 }) // 关联分析

// 报告生成 API
healthManager.report.daily({ date }) // 日报
healthManager.report.weekly({ startDate }) // 周报
healthManager.report.handbook() // 健康手册

// 提醒管理 API
healthManager.reminder.add({ type, schedule, message })
healthManager.reminder.list()
healthManager.reminder.remove(id)
```

## 7. 隐私和安全考虑

### 7.1 数据隐私
- 所有健康数据本地存储优先
- 数据传输加密 (TLS)
- 数据匿名化处理 (如需上传分析)
- 用户明确同意数据共享

### 7.2 安全措施
- 本地数据库加密
- 访问控制和身份验证
- 定期安全审计
- 漏洞报告机制

### 7.3 合规性
- 符合 HIPAA (医疗数据隐私标准)
- 符合 GDPR (欧盟数据保护条例)
- 符合中国个人信息保护法

## 8. 后续扩展方向

### 8.1 功能扩展
- 饮食记录和营养分析
- 睡眠质量监测
- 心理健康评估
- 家庭健康管理 (多用户)

### 8.2 技术扩展
- 区块链健康数据存证
- 联邦学习隐私保护分析
- 边缘计算实时分析
- AR/VR 健康数据可视化

### 8.3 生态集成
- 与电子健康记录系统集成
- 与保险公司合作 (健康奖励)
- 与医疗机构对接 (远程医疗)
- 与健康社区平台联动

---

**设计完成时间**: 2026-03-09  
**设计者**: Health Manager Skill 设计团队  
**版本**: 1.0.0