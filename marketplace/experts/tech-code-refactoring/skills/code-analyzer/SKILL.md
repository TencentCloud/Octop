---
name: code-analyzer
description: 深度代码分析工具。分析代码架构、执行流程、数据流、业务规则、外部依赖、数据模型，支持 DDD 模式识别（聚合根、实体、值对象、领域服务、仓储、领域事件、限界上下文）。使用场景：新代码库熟悉、架构文档生成、代码审查准备、技术债务评估、知识传承、DDD 模式识别。支持 Python、JavaScript、TypeScript、Rust、Java、Go 等 20+ 语言。
---

# Code Analyzer - 深度代码分析

专业的深度代码库分析工具，超越表面指标，深入理解：

- 🏗️ **架构风格** - 识别 MVC、Clean Architecture、微服务等
- 🚀 **执行流程** - 入口点、调用图、执行路径追踪
- 💧 **数据流动** - 数据如何在系统中传输和转换
- 📜 **业务规则** - 从代码中提取验证逻辑、业务约束
- 🔗 **外部依赖** - API、数据库、第三方服务
- 📊 **数据模型** - 实体、DTO、值对象及其关系
- 🏛️ **DDD 模式** - 聚合根、实体、值对象、领域服务

## 快速开始

```bash
# 完整深度分析
python3 scripts/analyze.py --path /path/to/project --output report.md

# DDD 专项分析
python3 scripts/ddd-analyzer.py --path /path/to/project --output ddd-report.md

# 排除特定目录
python3 scripts/analyze.py --path . --exclude "node_modules,vendor,target" --output analysis.md
```

## 核心功能

### 📊 代码质量评估

| 维度 | 说明 |
|------|------|
| **可维护性** | 代码结构、复杂度、可读性 |
| **可测试性** | 单元测试覆盖率、可测试程度 |
| **文档完整性** | 注释、文档覆盖率 |
| **复杂度** | 圈复杂度、耦合度 |

### 🏛️ DDD 模式识别

| 模式 | 识别能力 |
|------|----------|
| **聚合根** | ✅ 识别一致性边界 |
| **实体** | ✅ 识别有身份的对象 |
| **值对象** | ✅ 识别不可变对象 |
| **领域服务** | ✅ 识别无状态业务逻辑 |
| **仓储** | ✅ 识别持久化抽象 |
| **领域事件** | ✅ 识别事件驱动模式 |
| **限界上下文** | ✅ 识别模块边界 |

### 📝 报告生成

- 执行摘要
- 质量评分
- 问题清单（分级）
- 改进建议（分优先级）
- 架构图（Mermaid）

## 输出示例

```markdown
# 代码分析报告

## 执行摘要
- 总文件数：105
- 总代码行数：24,780
- 架构风格：Layered
- 入口点：5 个
- 数据模型：45 个
- 业务规则：23 个

## 质量指标
| 指标 | 评分 | 状态 |
|------|------|------|
| 可维护性 | 75/100 | 👍 |
| 可测试性 | 82/100 | ✅ |
| 文档完整性 | 68/100 | ⚠️ |
| 复杂度 | 71/100 | 👍 |

## 发现的问题
### 严重 (1)
- 循环依赖：module_a ↔ module_b

### 主要 (3)
- 高复杂度函数：calculate_score (复杂度=25)
- 过大文件：admin.py (850 行)
```

## 支持语言

| 语言 | 扩展名 | 分析深度 |
|------|--------|----------|
| Python | .py | 深度 (AST) |
| JavaScript | .js | 深度 |
| TypeScript | .ts | 深度 |
| Rust | .rs | 深度 |
| Java | .java | 中等 |
| Go | .go | 中等 |
| C/C++ | .c, .cpp | 基础 |

## 使用场景

### 1. 新项目熟悉
```bash
python3 scripts/analyze.py --path /new/project --output onboarding.md
```

### 2. 架构文档生成
```bash
python3 scripts/analyze.py --path . --output architecture.md
```

### 3. 代码审查准备
```bash
python3 scripts/analyze.py --path ./feature --output pr-analysis.md
```

### 4. 技术债务评估
```bash
python3 scripts/analyze.py --path . --exclude "tests" --output debt-review.md
```

### 5. DDD 模式识别
```bash
python3 scripts/ddd-analyzer.py --path . --output ddd-analysis.md
```

## 与 AI 助手配合

**Claude/Codex:**
```
"分析这个代码库并解释：
1. 主要入口点是什么？
2. 核心数据模型有哪些？
3. 编码了哪些业务规则？
4. 数据如何在系统中流动？"
```

AI 会：
1. 运行 code-analyzer
2. 解读分析报告
3. 提供针对性解释
4. 回答具体问题

## 最佳实践

详见 [references/best-practices.md](references/best-practices.md)：
- 代码分析方法论
- 架构识别技巧
- DDD 模式识别指南
- 质量改进建议

## 参见

- [OpenClaw 文档](https://docs.openclaw.ai)
- [ClawHub Skills](https://clawhub.com)
