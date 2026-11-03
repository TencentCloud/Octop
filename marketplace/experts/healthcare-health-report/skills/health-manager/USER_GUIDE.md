# Health Manager 用户指南

> 从零开始，轻松掌握健康管理

---

## 目录

1. [快速入门](#快速入门)
2. [记录血压数据](#记录血压数据)
3. [记录心率数据](#记录心率数据)
4. [记录运动数据](#记录运动数据)
5. [记录用药数据](#记录用药数据)
6. [查看趋势分析](#查看趋势分析)
7. [生成健康手册](#生成健康手册)
8. [设置智能提醒](#设置智能提醒)
9. [数据导入导出](#数据导入导出)
10. [常见问题](#常见问题)

---

## 快速入门

### 第一步：初始化

首次使用时，需要进行简单初始化：

```bash
health-manager init
```

系统会引导你完成基础配置：

```
欢迎使用 Health Manager！
请设置个人信息：

👤 姓名：张三
🎂 年龄：45
⚧ 性别 (male/female)：male
📏 身高 (cm)：175
⚖️ 体重 (kg)：72

配置已保存到 ~/.health-manager/config.json
```

### 第二步：第一条记录

让我们记录第一次血压数据：

```bash
health-manager record bp -s 120 -d 80 -p 72
```

参数说明：
- `-s` 或 `--systolic`: 收缩压（高压）
- `-d` 或 `--diastolic`: 舒张压（低压）
- `-p` 或 `--pulse`: 脉搏

成功后会显示：
```
✅ 血压记录已保存
   时间: 2026-03-09 08:30
   血压: 120/80 mmHg
   脉搏: 72 bpm
```

### 第三步：查看记录

```bash
health-manager list --recent 7
```

显示最近7天的所有记录。

---

## 记录血压数据

### 基础记录

```bash
# 最简形式
health-manager record bp -s 120 -d 80

# 包含脉搏
health-manager record bp -s 120 -d 80 -p 72

# 添加备注
health-manager record bp -s 120 -d 80 -p 72 --notes "晨起测量"
```

### 详细记录

```bash
# 指定测量体位
health-manager record bp -s 120 -d 80 -p 72 \
  --position sitting \
  --notes "坐着测量"

# 指定测量手臂
health-manager record bp -s 120 -d 80 -p 72 \
  --arm left \
  --notes "左臂测量"

# 完整记录
health-manager record bp -s 120 -d 80 -p 72 \
  --position sitting \
  --arm left \
  --notes "晨起，左臂，坐姿测量"
```

### 参数说明

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--systolic` | `-s` | 收缩压（高压）mmHg | `-s 120` |
| `--diastolic` | `-d` | 舒张压（低压）mmHg | `-d 80` |
| `--pulse` | `-p` | 脉搏 bpm | `-p 72` |
| `--position` | - | 体位 (sitting/standing/lying) | `--position sitting` |
| `--arm` | - | 手臂 (left/right) | `--arm left` |
| `--notes` | - | 备注信息 | `--notes "晨起测量"` |
| `--timestamp` | - | 自定义时间 | `--timestamp "2026-03-09T08:30:00"` |

### 血压分级参考

根据中国高血压防治指南：

| 分级 | 收缩压 | 舒张压 | 状态 |
|------|--------|--------|------|
| 正常 | <120 | <80 | ✅ 正常 |
| 正常高值 | 120-139 | 80-89 | ⚠️ 关注 |
| 高血压1级 | 140-159 | 90-99 | ⚠️ 轻度 |
| 高血压2级 | 160-179 | 100-109 | ⚠️ 中度 |
| 高血压3级 | ≥180 | ≥110 | 🚨 重度 |

Health Manager 会自动识别并给出提示。

---

## 记录心率数据

### 基础记录

```bash
# 最简形式
health-manager record hr --rate 68

# 指定活动状态
health-manager record hr --rate 68 --activity resting

# 添加设备来源
health-manager record hr --rate 68 --device "Apple Watch"
```

### 活动状态

```bash
# 静息心率
health-manager record hr --rate 68 --activity resting

# 运动后心率
health-manager record hr --rate 120 --activity exercise

# 睡眠心率
health-manager record hr --rate 58 --activity sleeping
```

### 参数说明

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--rate` | `-r` | 心率值 bpm | `--rate 68` |
| `--activity` | - | 活动状态 | `--activity resting` |
| `--device` | - | 测量设备 | `--device "Apple Watch"` |
| `--notes` | - | 备注信息 | `--notes "晨起静息"` |

### 心率参考范围

| 状态 | 正常范围 | 说明 |
|------|----------|------|
| 静息心率 | 60-100 bpm | 清醒安静状态 |
| 运动心率 | 因人而异 | 取决于运动强度 |
| 睡眠心率 | 50-70 bpm | 深睡时更低 |

---

## 记录运动数据

### 基础记录

```bash
# 最简形式
health-manager record ex --type running --duration 30

# 包含卡路里
health-manager record ex --type running --duration 30 --calories 280

# 包含距离
health-manager record ex --type running --duration 30 --distance 5.2
```

### 常见运动类型

```bash
# 跑步
health-manager record ex --type running --duration 30 --distance 5.2

# 游泳
health-manager record ex --type swimming --duration 45

# 骑行
health-manager record ex --type cycling --duration 60 --distance 20

# 力量训练
health-manager record ex --type strength --duration 45

# 瑜伽
health-manager record ex --type yoga --duration 60

# 散步
health-manager record ex --type walking --duration 30 --distance 2.5
```

### 详细记录

```bash
# 包含心率数据
health-manager record ex \
  --type running \
  --duration 30 \
  --distance 5.2 \
  --calories 280 \
  --hr-avg 135 \
  --hr-max 158

# 添加备注
health-manager record ex \
  --type running \
  --duration 30 \
  --notes "晨跑，天气晴朗，状态很好"
```

### 参数说明

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--type` | `-t` | 运动类型 | `--type running` |
| `--duration` | `-d` | 时长（分钟） | `--duration 30` |
| `--distance` | - | 距离（公里） | `--distance 5.2` |
| `--calories` | - | 消耗卡路里 | `--calories 280` |
| `--hr-avg` | - | 平均心率 | `--hr-avg 135` |
| `--hr-max` | - | 最大心率 | `--hr-max 158` |
| `--notes` | - | 备注信息 | `--notes "晨跑"` |

---

## 记录用药数据

### 基础记录

```bash
# 最简形式
health-manager record med --name "降压药" --dosage "1片"

# 标记已服用
health-manager record med --name "降压药" --dosage "1片" --taken

# 指定时间
health-manager record med --name "降压药" --dosage "1片" --time "08:00"
```

### 多种药物

```bash
# 同时服用多种药物
health-manager record med \
  --name "降压药" \
  --dosage "1片"

health-manager record med \
  --name "维生素D" \
  --dosage "1粒" \
  --notes "餐后服用"
```

### 参数说明

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--name` | `-n` | 药品名称 | `--name "降压药"` |
| `--dosage` | - | 剂量 | `--dosage "1片"` |
| `--time` | - | 服药时间 | `--time "08:00"` |
| `--taken` | - | 标记已服用 | `--taken` |
| `--notes` | - | 备注信息 | `--notes "餐后服用"` |

---

## 查看趋势分析

### 基础分析

```bash
# 分析最近30天血压趋势
health-manager analyze bp --period 30d

# 分析最近7天心率变化
health-manager analyze hr --period 7d

# 分析本月运动情况
health-manager analyze ex --period month
```

### 生成图表

```bash
# 生成血压趋势图
health-manager analyze bp --period 30d --chart

# 保存图表
health-manager analyze bp --period 30d --chart --output bp-trend.png
```

### 综合分析

```bash
# 分析所有健康数据
health-manager analyze --all --period 90d

# 生成综合报告
health-manager report --period month
```

### 分析报告示例

```
📊 血压分析报告 (最近30天)

数据概况：
- 记录次数：58次
- 平均血压：122/79 mmHg
- 平均脉搏：72 bpm

趋势分析：
- 收缩压趋势：稳定 ↗ 轻微上升
- 舒张压趋势：稳定 → 无明显变化
- 脉搏趋势：稳定 → 无明显变化

异常检测：
- 高血压预警：3次 (5.2%)
- 低血压预警：0次 (0%)

建议：
✅ 血压整体控制良好
⚠️ 收缩压略有上升趋势，建议增加监测频率
```

---

## 生成健康手册

### 月度手册

```bash
# 生成本月健康手册（PDF格式）
health-manager handbook --period month

# 指定输出路径
health-manager handbook --period month --output ~/健康手册-202603.pdf
```

### 季度报告

```bash
# 生成季度报告
health-manager handbook --period quarter

# 生成上季度报告
health-manager handbook --period last-quarter
```

### 年度总结

```bash
# 生成年度健康总结
health-manager handbook --period year

# HTML格式
health-manager handbook --period year --format html

# 包含所有详细数据
health-manager handbook --period year --include all
```

### 手册内容

健康手册包含以下内容：

1. **个人档案**
   - 基本信息
   - 健康目标
   - 目标完成情况

2. **血压分析**
   - 记录统计
   - 趋势图表
   - 异常提醒
   - 改进建议

3. **心率分析**
   - 静息心率趋势
   - 运动心率分布
   - 异常检测

4. **运动统计**
   - 运动频率
   - 运动时长
   - 卡路里消耗
   - 目标达成情况

5. **用药记录**
   - 用药依从性
   - 服药时间分布

6. **健康建议**
   - 基于数据的个性化建议
   - 目标调整建议

---

## 设置智能提醒

### 用药提醒

```bash
# 添加每日两次用药提醒
health-manager remind add med \
  --name "降压药" \
  --time "08:00,20:00"

# 仅工作日提醒
health-manager remind add med \
  --name "降压药" \
  --time "08:00" \
  --days "mon,tue,wed,thu,fri"

# 自定义提醒信息
health-manager remind add med \
  --name "降压药" \
  --time "08:00" \
  --message "该吃降压药啦，记得餐后服用"
```

### 监测提醒

```bash
# 添加血压监测提醒
health-manager remind add monitor \
  --type blood-pressure \
  --time "07:00,21:00"

# 添加心率监测提醒
health-manager remind add monitor \
  --type heart-rate \
  --time "09:00"
```

### 运动提醒

```bash
# 添加晨跑提醒（周一、三、五）
health-manager remind add ex \
  --type "晨跑" \
  --time "06:30" \
  --days "mon,wed,fri"

# 添加晚间散步提醒
health-manager remind add ex \
  --type "散步" \
  --time "19:00" \
  --days "mon,tue,wed,thu,fri,sat,sun"
```

### 管理提醒

```bash
# 查看所有提醒
health-manager remind list

# 输出示例：
# ID           类型        名称        时间              日期
# remind-001   用药        降压药      08:00, 20:00     每天
# remind-002   监测        血压        07:00, 21:00     每天
# remind-003   运动        晨跑        06:30            周一三五

# 删除提醒
health-manager remind remove --id remind-001

# 暂停提醒
health-manager remind pause --id remind-001

# 恢复提醒
health-manager remind resume --id remind-001
```

### 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--name` | 药品名称 | `--name "降压药"` |
| `--type` | 提醒类型 | `--type blood-pressure` |
| `--time` | 提醒时间（支持多个） | `--time "08:00,20:00"` |
| `--days` | 重复日期 | `--days "mon,wed,fri"` |
| `--message` | 自定义消息 | `--message "该吃药啦"` |

---

## 数据导入导出

### 导出数据

```bash
# 导出所有数据（JSON格式）
health-manager export --format json --output ~/health-data.json

# 导出血压数据
health-manager export bp --format json --output bp-data.json

# 导出为CSV格式
health-manager export --format csv --output health-data.csv

# 导出特定时间范围
health-manager export --from 2026-01-01 --to 2026-03-09
```

### 导入数据

```bash
# 从JSON文件导入
health-manager import --file health-data.json

# 从Apple Health导出文件导入
health-manager import --source apple-health --file export.xml

# 从CSV文件导入
health-manager import --file health-data.csv --format csv
```

### 数据备份

```bash
# 创建备份
health-manager backup --output ~/health-backup-20260309.tar.gz

# 从备份恢复
health-manager restore --file ~/health-backup-20260309.tar.gz
```

---

## 常见问题

### Q1: 如何修改个人信息？

```bash
# 修改姓名
health-manager config set user.name "李四"

# 修改年龄
health-manager config set user.age 50

# 修改体重
health-manager config set user.weight_kg 70

# 查看当前配置
health-manager config list
```

### Q2: 如何设置健康目标？

```bash
# 设置血压目标
health-manager config set targets.blood_pressure.systolic_max 130
health-manager config set targets.blood_pressure.diastolic_max 85

# 设置运动目标
health-manager config set targets.exercise.weekly_minutes 150
health-manager config set targets.exercise.daily_steps 8000
```

### Q3: 数据存储在哪里？

数据默认存储在 `~/.health-manager/` 目录：

```
~/.health-manager/
├── config.json          # 配置文件
├── data/                # 健康数据
│   ├── blood-pressure.json
│   ├── heart-rate.json
│   ├── exercise.json
│   └── medication.json
├── reports/             # 生成的报告
└── cache/               # 缓存数据
```

### Q4: 如何删除错误记录？

```bash
# 查看记录ID
health-manager list bp --show-id

# 删除特定记录
health-manager delete --id bp-20260309-001
```

### Q5: 提醒不生效怎么办？

```bash
# 检查提醒服务状态
health-manager remind status

# 重启提醒服务
health-manager remind restart

# 检查系统通知权限
health-manager check-permissions
```

### Q6: 如何与医生分享数据？

```bash
# 生成可分享的PDF报告
health-manager handbook --period month --share

# 导出标准格式数据
health-manager export --format csv --output medical-records.csv
```

### Q7: 支持哪些设备数据导入？

目前支持：
- **Apple Health**: XML 导出文件
- **Google Fit**: OAuth 同步
- **小米手环**: JSON 导入
- **华为健康**: JSON 导入

```bash
# 查看支持的导入格式
health-manager import --help
```

### Q8: 如何从其他应用迁移数据？

1. 从原应用导出数据（CSV/JSON格式）
2. 使用 `health-manager import` 导入
3. 验证数据完整性：

```bash
health-manager validate --file imported-data.json
```

---

## 小贴士

### 💡 测量血压最佳时间

- **早晨**: 起床后1小时内，服药前，早餐前
- **晚上**: 睡前，服药后
- **固定时间**: 每天在相同时间测量

### 💡 准确测量要点

1. 测量前休息5分钟
2. 坐姿端正，双脚平放
3. 手臂与心脏同高
4. 不要憋尿
5. 避免咖啡、运动后立即测量

### 💡 建立健康习惯

1. **定时提醒**: 设置固定时间的测量提醒
2. **及时记录**: 测量后立即记录，避免遗忘
3. **定期回顾**: 每周查看趋势分析
4. **目标驱动**: 设定合理的健康目标
5. **分享反馈**: 与医生分享健康手册

---

## 获取帮助

```bash
# 查看帮助
health-manager --help

# 查看特定命令帮助
health-manager record --help
health-manager analyze --help
health-manager handbook --help

# 在线文档
health-manager docs
```

---

## 版本历史

- **v1.0.0** (2026-03-09)
  - 初始版本发布
  - 血压、心率、运动、用药记录
  - 趋势分析和图表生成
  - 健康手册生成
  - 智能提醒功能

---

**祝你健康每一天！** 🌟