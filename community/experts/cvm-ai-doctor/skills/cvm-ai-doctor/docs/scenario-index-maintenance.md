# 场景索引 - 维护文档

> **本文档供人类维护者使用**，描述场景索引的设计思路、维护流程和统计数据。
> AI 不需要读取此文件。AI 路由表见 `references/00-scenario-index.md`。

---

## 设计架构

### 整体定位

`00-scenario-index.md` 是 SKILL.md 的 **Tier 2 路由表**：

```
SKILL.md (Tier 1: 10 核心场景, 80% 覆盖)
  ↓ 匹配不到
00-scenario-index.md (Tier 2: 60+ 扩展场景, 20% 长尾)
  ↓ 匹配到
commands/*.md 或 references/*.md (具体执行)
```

### AI 使用流程

```
用户描述问题
  ↓
1. 在索引中匹配场景 (关键词搜索, ~10 秒)
  ↓
2. 根据推荐的 Reference 运行 Quick Mode (10 秒)
   → 使用匹配当前 OS 的命令变体
  ↓
3. 如果 Quick Mode 发现异常 → 运行 Deep Mode (20-60 秒)
   → Commands 文件中有完整的平台命令表可参考
  ↓
4. 报告结果 + 修复建议
```

### 匹配规则

- **关键词触发**: 用户说的关键词 → 查找对应场景
- **中英文**: "慢" = "slow", "卡" = "lag"
- **模糊匹配**: "内存不够" → "内存问题"
- **默认回退**: 无匹配 → 场景 3.1（综合健康检查）

---

## AI 决策算法 (伪代码)

以下是 AI 场景匹配和执行流程的概念描述，用于理解设计意图：

```python
def match_scenario(user_query):
    """根据用户查询匹配场景"""
    keywords = extract_keywords(user_query)
    
    # 1. 精确匹配
    for keyword in keywords:
        if scenario := exact_match(keyword):
            return scenario
    
    # 2. 模糊匹配
    for keyword in keywords:
        if scenario := fuzzy_match(keyword):
            return scenario
    
    # 3. 默认场景（综合健康检查）
    return scenario_3_1

def execute_scenario(scenario, user_query):
    """执行场景推荐路径"""
    path = scenario.recommended_path
    
    # Step 1: Quick Mode
    if "reference" in path.step1:
        quick_result = run_quick_mode(path.step1)
    
    # Step 2: 决策是否 Deep
    if should_run_deep(quick_result, user_query):
        deep_result = run_deep_mode(path.step2, quick_result.focus)
        return generate_report(quick_result, deep_result)
    else:
        return generate_report(quick_result)

def should_run_deep(quick_result, user_query):
    """决定是否运行 Deep Mode"""
    if quick_result.has_critical():
        return True  # 自动触发
    elif quick_result.has_warning():
        if "troubleshoot" in user_query or "慢" in user_query:
            return True  # 自动触发
        else:
            return ask_user("发现异常，是否深度分析？")
    return False  # 不需要 Deep
```

---

## 使用示例

### 示例 1: 用户说"服务器很慢"

```
AI 决策流程:
1. 在索引中搜索 "慢" → 匹配到场景 1.1
2. 查看推荐路径:
   - Step 1: resource-saturation-quick.md
3. 运行 Quick Mode (10 秒)
4. Quick 结果: Memory WARNING
5. 触发 Deep Mode: resource-saturation-deep-memory.md (20 秒)
6. Deep 结果: Java 内存泄漏
7. 生成报告 + 修复建议
```

### 示例 2: 用户说"磁盘坏了"

```
AI 决策流程:
1. 在索引中搜索 "磁盘坏" → 匹配到场景 5.2
2. 查看推荐路径:
   - Step 1: disk-smart-quick.md
3. Quick 结果: SMART CRITICAL
4. 触发 Deep Mode: disk-smart-deep.md
5. Deep 结果: Reallocated sectors 100+
6. 报告: 磁盘即将失效，建议立即备份
```

### 示例 3: 用户说"检查系统健康"

```
AI 决策流程:
1. 在索引中搜索 "健康检查" → 匹配到场景 3.1
2. 查看推荐路径:
   - Step 1: 运行 3 个 Quick 检查
   - resource-saturation-quick.md
   - system-logs-quick.md
   - disk-smart-quick.md
3. 全部 OK → 报告正常
4. 如有异常 → 触发对应 Deep Mode
```

---

## 统计信息

### 覆盖范围
- **总场景数**: 20 大类 + 60+ 细分场景
- **Commands 覆盖**: 126 个文件
- **References 覆盖**: 5 个核心诊断模块
- **预计覆盖率**: 95%+ 常见用户问题

### 场景分布
- **高频场景** (⭐⭐⭐⭐⭐): 6 大类，20 个场景 → 80% 用户问题
- **中频场景** (⭐⭐⭐⭐): 4 大类，15 个场景 → 15% 用户问题
- **低频场景** (⭐⭐⭐): 10 大类，25+ 场景 → 5% 用户问题

### 预期效果
- **匹配准确度**: 90%+
- **首次响应时间**: 10 秒（Quick Mode）
- **完整诊断时间**: 30-70 秒（Quick + Deep）
- **Token 节省**: 70-80%

---

## 维护指南

### 更新频率
- **高频场景**: 每月检查一次
- **中低频场景**: 每季度检查一次
- **新增 Command/Reference**: 立即更新索引

### 更新流程
1. 识别新场景或 Command
2. 分析用户关键词
3. 确定优先级（⭐⭐⭐⭐⭐ / ⭐⭐⭐⭐ / ⭐⭐⭐）
4. 添加到对应分类
5. 更新快速查找表
6. 测试 AI 匹配准确度

### 文件结构说明

```
references/
  00-scenario-index.md          ← AI 路由表（精简版,只含场景匹配信息）
  resource-saturation-*.md      ← 资源饱和度诊断模块
  system-logs-*.md              ← 系统日志诊断模块
  disk-smart-*.md               ← 磁盘 SMART 诊断模块
  hardware-other.md             ← 硬件健康诊断模块
  time-sync.md                  ← 时间同步诊断模块

docs/
  architecture.md               ← 系统架构设计文档
  scenario-decision-guide.md    ← 扩展场景决策指南
  scenario-index-maintenance.md ← 本文件（维护文档）
```

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-03-24 | 初始版本，完整场景索引 |
| 2.0 | 2026-03-24 | 精简为 AI 路由表（~420 行），人类维护文档独立至 docs/ |

---

**维护者**: AI Assistant
**状态**: 生产就绪
