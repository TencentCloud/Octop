---
name: design-prd-writing
description: >-
  PRD 撰写专家包。适用于PRD 撰写、从多轮对话式需求探索与EPIC分解、RICE优先级排序与客户访谈分析框架、到结构化PRD创建（含用户故事与验收标准）、
  专业PRD撰写润色、PRD转设计需求文档（信息架构/交互流程/页面布局）、再到PRD量化评审打分的完整PRD撰写工作流等场景；
  也适用于用户明确要求调用「PRD 撰写 / PRD 撰写专家包 / PRD Writing」。
version: 1.0.0
metadata:
  author: SkillHub
  package_type: meta-skill
  display_name: PRD 撰写
  aliases:
    - PRD 撰写
    - PRD 撰写专家包
    - PRD 撰写技能包
    - PRD Writing
    - design-prd-writing
    - prd-writing
orchestration:
  children:
    - requirements-analysis
    - software-manager-skill
    - prd
    - prd-writer-pro
    - prd-to-design-doc
    - prd-reviewer
compatibility: SkillHub meta-skill, exportable to Claude Code / Codex markdown skill.
---
# PRD 撰写工作流

你现在要完成一项产品需求文档（PRD）的撰写任务。你已安装以下 Skill，请按步骤串联使用：

## 步骤 1：需求探索与结构化（获取层）
使用 **requirements-analysis** 完成：
- 通过多轮对话将用户的简短想法转化为详细需求
- 将 EPIC 分解为具体需求项和用户故事
- 识别利益相关者和依赖关系
- 定义每个需求的验收标准
- 对多个需求进行初步分类和关联

输出结构化需求清单和用户故事列表。

## 步骤 2：优先级排序与框架选型（分析层）
使用 **Software Manager Skill** 完成：
- 使用 RICE 框架（Reach/Impact/Confidence/Effort）对需求排序
- 结合客户访谈数据验证需求假设
- 选择合适的 PRD 模板和文档结构
- 制定产品路线图和版本规划
- 确定 MVP 范围和迭代策略

输出优先级排序表和 MVP 功能清单。

## 步骤 3：PRD 结构化创建（输出层）
使用 **Prd** 完成：
- 创建包含完整结构的产品需求文档
- 编写每个功能的用户故事（As a... I want... So that...）
- 定义详细的验收标准（Given/When/Then）
- 规划功能实现的任务拆解
- 关联需求间的依赖关系

输出结构化 PRD 框架文档。

## 步骤 4：PRD 专业撰写与润色（输出层）
使用 **PRD文档撰写助手Pro** 完成：
- 将结构化 PRD 转化为专业、完整的需求文档
- 补充背景描述、业务目标和成功指标
- 完善非功能需求（性能、安全、兼容性）
- 添加边界条件和异常处理说明
- 确保文档语言清晰、逻辑严谨、无歧义

输出专业级 PRD 文档。

## 步骤 5：PRD 转设计需求文档（输出层）
使用 **产品prd转设计文档** 完成：
- 将 PRD 转换为设计团队可直接使用的设计需求文档
- 输出信息架构图和页面层级关系
- 生成交互流程图（含异常流程）
- 定义页面布局规范和视觉要求
- 自动生成 Mermaid 格式的交互流程图

输出设计需求文档和交互流程图。

## 步骤 6：PRD 量化评审（输出层）
使用 **Prd Reviewer** 完成：
- 对 PRD 进行 10 分制严格量化评审
- 逐模块评分（完整性、清晰度、可执行性、一致性等）
- 标注具体扣分项和改进建议
- 识别逻辑漏洞、遗漏场景和模糊描述
- 生成评审报告，指导 PRD 迭代优化

输出评审评分表和改进建议。

## 最终输出
将以上步骤的结果整合为完整的 PRD 撰写包，交付以下文件：
1. **需求清单**：结构化需求列表、用户故事和优先级排序
2. **PRD 文档**：专业完整的产品需求文档
3. **设计需求文档**：信息架构、交互流程、页面布局规范
4. **评审报告**：量化评分、扣分说明和迭代优化建议
