# exercise-teaching — 动作教学

## 触发场景
- 用户问"XX怎么做""这个动作怎么练""教我XX动作""XX动作教学"
- 用户说不清具体动作，需要推荐

## 操作规范

### 1. 查询动作详情
```bash
python scripts/query_exercises.py --id "Incline_Dumbbell_Press" --detailed
```

### 2. 输出结构
按以下顺序输出：

**基本信息**
- 动作名称（中英文）、难度等级、器械需求、目标肌群

**动作步骤**
- 将 instructions 翻译成中文，简洁易懂
- 每步一句话，突出关键动作要领

**训练建议**
- 推荐组数、次数范围、组间休息时间
- 根据目标调整（增肌8-12次、力量3-6次、耐力15+次）

**示范图片**
- 输出图片路径：`free-exercise-db/exercises/[动作ID]/images/0.jpg`
- 在支持图片的平台直接发送图片

### 3. 注意事项
- 标注常见错误（如腰椎过度弯曲、借力过多）
- 有伤病风险的动作标注安全提醒
- 根据用户经验调整教学深度（新手更详细，老手更精炼）

### 4. 模糊需求处理
用户没说具体动作时：
- 根据当前训练计划推荐相关动作教学
- 或提供2-3个候选动作让用户选择

## 依赖
- [references/exercise-db-schema.md](../references/exercise-db-schema.md) — 数据库字段说明
