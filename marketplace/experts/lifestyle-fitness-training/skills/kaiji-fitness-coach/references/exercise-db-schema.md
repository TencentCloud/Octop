# Free Exercise DB 数据库结构

## 概述

[free-exercise-db](https://gitee.com/kaiji1126/free-exercise-db) 是一个开源的健身动作数据库，包含 800+ 个动作的详细信息。

## 数据库位置

```
技能目录/
├── free-exercise-db/
│   ├── exercises/           # 单个动作 JSON 文件
│   │   ├── Incline_Dumbbell_Press/
│   │   │   ├── exercise.json
│   │   │   └── images/
│   │   │       ├── 0.jpg
│   │   │       └── 1.jpg
│   │   └── ...
│   └── dist/
│       └── exercises.json   # 所有动作的合并文件
```

## 动作数据结构

### exercise.json 字段

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| id | string | 动作唯一标识 | "Incline_Dumbbell_Press" |
| name | string | 动作名称 | "Incline Dumbbell Press" |
| force | string | 发力类型 | "push" / "pull" / "static" |
| level | string | 难度等级 | "beginner" / "intermediate" / "expert" |
| mechanic | string | 动作类型 | "compound" / "isolation" |
| equipment | string | 所需器械 | 见下表 |
| primaryMuscles | array | 主要目标肌群 | ["chest"] |
| secondaryMuscles | array | 次要参与肌群 | ["shoulders", "triceps"] |
| instructions | array | 动作步骤 | ["步骤1", "步骤2", ...] |
| category | string | 训练类别 | 见下表 |
| images | array | 示范图片文件名 | ["0.jpg", "1.jpg"] |

### 完整示例

```json
{
  "id": "Incline_Dumbbell_Press",
  "name": "Incline Dumbbell Press",
  "force": "push",
  "level": "beginner",
  "mechanic": "compound",
  "equipment": "dumbbell",
  "primaryMuscles": ["chest"],
  "secondaryMuscles": ["shoulders", "triceps"],
  "instructions": [
    "Lie back on an incline bench with a dumbbell in each hand on top of your thighs...",
    "Then, using your thighs to help push the dumbbells up, lift the dumbbells one at a time...",
    "Turn your wrists so that the palms of your hands are facing away from you...",
    "Be sure to keep full control of the dumbbells at all times...",
    "Breathe out and push the dumbbells up with your chest...",
    "Lock your arms at the top, hold for a second, and then start slowly lowering the weight...",
    "Repeat the movement for the prescribed amount of repetitions..."
  ],
  "category": "strength",
  "images": ["0.jpg", "1.jpg"]
}
```

## 枚举值参考

### equipment（器械类型）

| 值 | 说明 | 中文 |
|----|------|------|
| barbell | 杠铃 | 杠铃 |
| dumbbell | 哑铃 | 哑铃 |
| cable | 龙门架/拉索 | 拉索 |
| machine | 固定器械 | 器械 |
| body only | 徒手 | 徒手 |
| kettlebells | 壶铃 | 壶铃 |
| bands | 弹力带 | 弹力带 |
| exercise ball | 健身球 | 健身球 |
| medicine ball | 药球 | 药球 |
| e-z curl bar | 曲杆 | 曲杆 |
| foam roll | 泡沫轴 | 泡沫轴 |
| other | 其他 | 其他 |

### primaryMuscles / secondaryMuscles（肌群）

| 值 | 说明 | 中文 |
|----|------|------|
| chest | 胸部 | 胸部 |
| lats | 背阔肌 | 背部宽度 |
| lower back | 下背部 | 下背 |
| middle back | 中背部 | 背部厚度 |
| traps | 斜方肌 | 斜方 |
| shoulders | 肩部 | 肩部 |
| biceps | 二头肌 | 二头 |
| triceps | 三头肌 | 三头 |
| forearms | 前臂 | 前臂 |
| quadriceps | 股四头肌 | 大腿前侧 |
| hamstrings | 腘绳肌 | 大腿后侧 |
| calves | 小腿 | 小腿 |
| glutes | 臀部 | 臀部 |
| abductors | 髋外展肌 | 髋外侧 |
| adductors | 髋内收肌 | 髋内侧 |
| abdominals | 腹部 | 核心/腹肌 |
| neck | 颈部 | 颈部 |

### force（发力类型）

| 值 | 说明 | 典型动作 |
|----|------|----------|
| push | 推类 | 卧推、推举、深蹲 |
| pull | 拉类 | 划船、引体、硬拉 |
| static | 静态 | 平板、支撑类 |

### level（难度等级）

| 值 | 说明 | 适用人群 |
|----|------|----------|
| beginner | 初级 | 新手，<6个月经验 |
| intermediate | 中级 | 进阶，6-24个月经验 |
| expert | 高级 | 高阶，>24个月经验 |

### mechanic（动作类型）

| 值 | 说明 | 特点 |
|----|------|------|
| compound | 复合动作 | 多关节，多肌群参与，力量增长 |
| isolation | 孤立动作 | 单关节，单肌群参与，感受度好 |

### category（训练类别）

| 值 | 说明 | 中文 |
|----|------|------|
| strength | 力量训练 | 力量 |
| powerlifting | 力量举 | 力量举 |
| olympic weightlifting | 奥林匹克举重 | 奥举 |
| plyometrics | 爆发力训练 | 爆发 |
| cardio | 有氧 | 有氧 |
| stretching | 拉伸 | 拉伸 |
| strongman | 壮汉训练 | 壮汉 |

## 查询参数组合示例

### 按目标查询

```bash
# 胸部哑铃动作
--muscle chest --equipment dumbbell

# 背部拉类动作
--force pull --muscle lats

# 腿部复合动作
--muscle quadriceps --mechanic compound

# 新手徒手动作
--level beginner --equipment "body only"
```

### 按训练日查询

```bash
# PUSH 日动作
--force push --equipment dumbbell

# PULL 日动作
--force pull --equipment dumbbell

# LEG 日动作
--muscle quadriceps --muscle hamstrings --muscle glutes
```

### 按难度查询

```bash
# 新手友好动作
--level beginner

# 进阶挑战动作
--level intermediate

# 高阶动作
--level expert
```

## 图片资源

### 路径格式

```
free-exercise-db/exercises/[动作ID]/images/[图片名]
```

### 示例

```
free-exercise-db/exercises/Incline_Dumbbell_Press/images/0.jpg
free-exercise-db/exercises/Incline_Dumbbell_Press/images/1.jpg
```

### 使用方式

1. 查询动作获取图片路径
2. 在支持的平台直接发送图片
3. 用于动作教学和示范

## 数据库更新

数据库会不定期更新，可以重新运行设置脚本：

```bash
python scripts/setup_db.py --update
```

这会从 Gitee 拉取最新版本。

## 常见查询场景

### 场景 1：给只有哑铃的用户设计计划

```bash
# 查询所有哑铃动作
--equipment dumbbell

# 按肌群细分
--equipment dumbbell --muscle chest
--equipment dumbbell --muscle lats
--equipment dumbbell --muscle quadriceps
```

### 场景 2：给新手设计入门计划

```bash
# 新手友好的复合动作
--level beginner --mechanic compound

# 新手徒手动作
--level beginner --equipment "body only"
```

### 场景 3：设计高强度训练

```bash
# 高阶动作
--level expert

# 爆发力训练
--category plyometrics
```

## 注意事项

1. **图片版权**：图片来自开源项目，使用时遵守开源协议
2. **动作说明**：说明是英文的，需要翻译成中文使用
3. **个体差异**：动作难度仅供参考，实际因人而异
4. **安全第一**：建议用户根据自身情况选择合适的动作
