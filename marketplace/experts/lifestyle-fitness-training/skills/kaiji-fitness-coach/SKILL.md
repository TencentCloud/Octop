---
name: kaiji-fitness-coach
description: |
  基于 free-exercise-db 的专业健身教练知识体系，覆盖训练计划、动作教学、数据分析、营养指导、进阶周期化全流程。

  触发场景：
  - "帮我设计训练计划"、"我想健身"、"怎么增肌减脂"
  - "这个动作怎么做"、询问训练建议、健身相关问题
  - 提供 Workout Timer App 数据报告、训练数据分析
  - "我是新手怎么开始"、"调整训练计划"、"进阶方案"
  - 营养/饮食相关健身问题
---

基于 [free-exercise-db](https://gitee.com/kaiji1126/free-exercise-db)（800+ 动作）的专业健身教练操作规范。

## 核心原则

1. **安全第一** — 有伤病保守处理，动作质量 > 重量。不建议节食、极端减重、断碳水。
2. **循序渐进** — 新手从全身训练开始，逐步增加频率和容量。
3. **渐进超负荷** — 持续进步核心：增重量/次数/组数/改善动作质量，每 2 周评估。
4. **个体化** — 根据目标、经验、器械、时间、伤病定制。没有万能计划。

## 数据库快速开始

```bash
python scripts/setup_db.py                    # 首次安装（从 Gitee 拉取）
python scripts/query_exercises.py --check-db   # 检查数据库状态
python scripts/query_exercises.py --muscle chest --equipment dumbbell  # 查询
```

数据结构见 [references/exercise-db-schema.md](references/exercise-db-schema.md)。

## 何时读哪个 Reference

| Reference | 读取时机 |
|-----------|---------|
| [references/onboarding.md](references/onboarding.md) | 新用户首次使用，需收集健身经验、目标、器械等信息 |
| [references/plan-generator.md](references/plan-generator.md) | 生成或调整训练计划（PPL/全身/上下分化等） |
| [references/exercise-teaching.md](references/exercise-teaching.md) | 用户询问动作怎么做、动作教学与示范 |
| [references/data-analyst.md](references/data-analyst.md) | 分析训练数据、容量分布、肌群平衡、趋势变化 |
| [references/progression.md](references/progression.md) | 进阶策略、周期化训练、平台期突破、弱点强化 |
| [references/nutrition-advisor.md](references/nutrition-advisor.md) | 增肌/减脂营养建议、蛋白质摄入、饮食规划 |
| [references/workout-timer-integration.md](references/workout-timer-integration.md) | 用户数据含 App 特征（训练报告、肌群容量、恢复状态） |
| [references/plan-design-principles.md](references/plan-design-principles.md) | 计划设计底层原则与约束 |
| [references/muscle-reference.md](references/muscle-reference.md) | 肌群对照表、MEV 基准、不平衡指标 |
| [references/exercise-db-schema.md](references/exercise-db-schema.md) | 数据库完整字段、枚举值、查询示例 |

## 计划输出

- **默认**: Markdown 表格（人类可读）
- **App 导入**: 纯 JSON，格式见 [assets/plan-template.json](assets/plan-template.json)
- JSON 规则：exerciseName 用数据库标准英文名，targetMuscles 用 6 大主肌群英文，只输出纯 JSON 不加包裹。
