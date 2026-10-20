---
name: plan
description: |
  仅计划模式——在 `plans/` 下编写可执行的 markdown 计划，不执行。
  当用户输入 /plan 或明确要求计划而非实现时触发。
version: 2.0.0
author: Octop (writing-craft adapted from obra/superpowers)
license: MIT
compatibility: linux, macos, windows
metadata:
  octop:
    label:
      zh: "计划模式"
      en: "Plan Mode"
    summary:
      zh: "只写可执行计划，不动手实现。"
      en: "Write an actionable plan without executing it."
  harness:
    emoji: "📋"
    tags: [planning, plan-mode, implementation, workflow, design, documentation]
    related_skills: [task-based execution, test-driven-development, requesting-code-review]
---

# 计划模式

## Harness-agent 工具

本技能从 Octop 移植。使用以下 harness/deepagents 工具：

| 概念 | 工具 |
|---------|------|
| Shell | `execute` |
| 读/写/编辑文件 | `read_file`, `write_file`, `edit_file` |
| 查找文件/搜索内容 | `glob`, `grep` |
| 获取 URL | `web_fetch` |
| 浏览器自动化 | `browser_use` |
| 子代理工作 | `task` |
| 记忆 | `memory_store`, `memory_recall`, `memory_search` |

内置技能文件位于 `/_builtin_skills/<name>/`。用户安装的技能位于 `/skills/<name>/`。

当用户需要计划而非执行时，使用此技能。

## 核心行为

在这一轮中，你只做计划：

- 不要实现代码。
- 不要编辑项目文件（计划 markdown 文件除外）。
- 不要运行变更性终端命令、提交、推送或执行外部操作。
- 你可以使用只读命令/工具检查仓库或其他上下文。
- 你的交付物是保存在活动工作区内 `plans/` 下的 markdown 计划。

## 输出要求

编写具体且可执行的 markdown 计划。

相关时包含：
- 目标
- 当前上下文/假设
- 提议的方法
- 分步计划
- 可能变更的文件
- 测试/验证
- 风险、权衡和开放问题

如果任务与代码相关，包含确切的文件路径、可能的测试目标和验证步骤。

## 保存位置

使用 `write_file` 保存到：
- `plans/YYYY-MM-DD_HHMMSS-<slug>.md`

将其视为相对于活动工作目录/backend 工作区。

如果运行时提供了特定目标路径，使用确切路径。
如果没有，在 `plans/` 下自己创建一个合理的时间戳文件名。

## 交互风格

- 如果请求足够清晰，直接编写计划。
- 如果没有明确指令伴随 `/plan`，从当前对话上下文推断任务。
- 如果确实未充分指定，提出简短的澄清问题而不是猜测。
- 保存计划后，简要回复你计划了什么以及保存路径。

---

# 写好计划

本技能的其余部分是编写*优秀*实施计划的技艺——即上述 markdown 文件内的内容。

## 概述

编写全面的实施计划，假设实施者对代码库零上下文且品味可疑。记录他们需要的一切：要接触哪些文件、完整代码、测试命令、要检查的文档、如何验证。给他们细粒度的任务。DRY。YAGNI。TDD。频繁提交。

假设实施者是一位熟练的开发者，但对工具集或问题领域几乎一无所知。假设他们不太了解好的测试设计。

**核心原则：** 好的计划让实施变得显而易见。如果有人需要猜测，说明计划不完整。

## 何时需要完整实施计划

**始终在之前使用：**
- 实施多步骤功能
- 分解复杂需求
- 通过基于任务的执行委派给子代理

**不要跳过当：**
- 功能看起来简单（假设会导致 bug）
- 你计划自己实施（未来的你需要指导）
- 独自工作（文档很重要）

## 细粒度任务

**每个任务 = 2-5 分钟的专注工作。**

每一步是一个动作：
- "编写失败测试" — 步骤
- "运行它以确保失败" — 步骤
- "实施最小代码使测试通过" — 步骤
- "运行测试并确保它们通过" — 步骤
- "提交" — 步骤

**太大：**
```markdown
### 任务1：构建认证系统
[跨 5 个文件的 50 行代码]
```

**正确大小：**
```markdown
### 任务1：创建带 email 字段的 User 模型
[10 行，1 个文件]

### 任务2：向 User 添加密码哈希字段
[8 行，1 个文件]

### 任务3：创建密码哈希工具
[15 行，1 个文件]
```

## 计划文档结构

### 头部（必需）

每个计划必须以以下内容开头：

```markdown
# [功能名称] 实施计划

> **给代理：** 使用基于任务的执行技能逐任务实施此计划。

**目标：** [一句话描述构建了什么]

**架构：** [关于方法的 2-3 句话]

**技术栈：** [关键技术/库]

---
```

### 任务结构

每个任务遵循此格式：

````markdown
### 任务 N：[描述性名称]

**目标：** 此任务完成什么（一句话）

**文件：**
- 创建：`exact/path/to/new_file.py`
- 修改：`exact/path/to/existing.py:45-67`（如果知道行号）
- 测试：`tests/path/to/test_file.py`

**步骤1：编写失败测试**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**步骤2：运行测试以验证失败**

运行：`pytest tests/path/test.py::test_specific_behavior -v`
预期：失败 — "function not defined"

**步骤3：编写最小实现**

```python
def function(input):
    return expected
```

**步骤4：运行测试以验证通过**

运行：`pytest tests/path/test.py::test_specific_behavior -v`
预期：通过

**步骤5：提交**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## 编写流程

### 步骤1：理解需求

阅读并理解：
- 功能需求
- 设计文档或用户描述
- 验收标准
- 约束

### 步骤2：探索代码库

使用 harness 文件系统工具理解项目：

```text
# 理解项目结构
glob(pattern="**/*.py", path="src/")

# 查看类似功能
grep(pattern="similar_pattern", path="src/")

# 列出测试文件
glob(pattern="tests/**/*.py")

# 读取关键文件
read_file("src/app.py")
```

### 步骤3：设计方法

决定：
- 架构模式
- 文件组织
- 需要的依赖
- 测试策略

### 步骤4：编写任务

按顺序创建任务：
1. 设置/基础设施
2. 核心功能（每个都 TDD）
3. 边界情况
4. 集成
5. 清理/文档

### 步骤5：添加完整细节

对于每个任务，包含：
- **确切文件路径**（不是"配置文件"而是 `src/config/settings.py`）
- **完整代码示例**（不是"添加验证"而是实际代码）
- **确切命令**与预期输出
- **验证步骤**证明任务有效

### 步骤6：审查计划

检查：
- [ ] 任务按顺序且逻辑清晰
- [ ] 每个任务细粒度（2-5 分钟）
- [ ] 文件路径确切
- [ ] 代码示例完整（可复制粘贴）
- [ ] 命令确切且预期输出明确
- [ ] 没有缺失的上下文
- [ ] 应用了 DRY、YAGNI、TDD 原则

## 原则

### DRY（不要重复自己）

**坏：** 在 3 个地方复制粘贴验证
**好：** 提取验证函数，到处使用

### YAGNI（你不会需要它）

**坏：** 为未来需求添加"灵活性"
**好：** 只实施现在需要的东西

```python
# 坏 — YAGNI 违反
class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email
        self.preferences = {}  # 还不需要！
        self.metadata = {}  # 还不需要！


# 好 — YAGNI
class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email
```

### TDD（测试驱动开发）

每个产生代码的任务应包含完整的 TDD 循环：
1. 编写失败测试
2. 运行以验证失败
3. 编写最小代码
4. 运行以验证通过

详情参见 `test-driven-development` 技能。

### 频繁提交

每个任务后提交：
```bash
git add [files]
git commit -m "type: description"
```

## 常见错误

### 模糊的任务

**坏：** "添加认证"
**好：** "创建带 email 和 password_hash 字段的 User 模型"

### 不完整的代码

**坏：** "步骤1：添加验证函数"
**好：** "步骤1：添加验证函数"后跟完整的函数代码

### 缺失验证

**坏：** "步骤3：测试它是否有效"
**好：** "步骤3：运行 `pytest tests/test_auth.py -v`，预期：3 个通过"

### 缺失文件路径

**坏：** "创建模型文件"
**好：** "创建：`src/models/user.py`"

## 执行交接

保存计划后，提供执行方法：

**"计划完成并已保存。准备使用 `task` 工具执行——每个计划任务一个子代理。我可以继续吗？"**

执行时：
- 每个计划任务使用来自保存计划的完整上下文进行新的 `task` 调度
- 在移动到下一个任务之前审查输出

## 记住

```
细粒度任务（每个 2-5 分钟）
确切文件路径
完整代码（可复制粘贴）
确切命令与预期输出
验证步骤
DRY、YAGNI、TDD
频繁提交
```

**好的计划让实施变得显而易见。**
