---
name: academic-literature-review
description: >-
  文献综述专家包。适用于文献综述、从透明严谨的双轮深度调研（APA引用/证据分级/用户确认）与专精文献综述论文分析学术写作、
  12要素结构化论文拆解（研究背景/问题/方法/贡献/不足/展望）与8阶段系统性中英文文献回顾、
  到论文大纲文献综述框架摘要生成引用格式规范与学术写作文献综述研究方法撰写的完整文献综述工作流、文献调研、论文拆解、综述撰写等场景；
  也适用于用户明确要求调用「文献综述 / 文献综述专家包 / Literature Review」。
version: 1.0.0
metadata:
  author: SkillHub
  package_type: meta-skill
  display_name: 文献综述
  aliases:
    - 文献综述
    - 文献综述专家包
    - 文献综述技能包
    - Literature Review
    - academic-literature-review
    - literature-review
orchestration:
  children:
    - academic-deep-research-pro
    - academic-researcher
    - paper-analyzer
    - ai-powered-literature-review-skills
    - thesis-helper
    - academic-writing
compatibility: SkillHub meta-skill, exportable to Claude Code / Codex markdown skill.
---
# 文献综述工作流

你现在要完成一项文献综述的撰写任务。你已安装以下 Skill，请按步骤串联使用：

## 步骤 1：双轮深度调研（获取层）
使用 **Academic Deep Research Pro** 完成：
- 对每个主题强制执行双轮调研确保覆盖全面
- 采用 APA 7 版引用格式标注所有来源
- 对证据进行分级评估（强/中/弱）
- 通过 3 次用户确认保证研究方向准确
- 生成详尽的调研报告和文献清单

输出双轮调研报告和分级证据清单。

## 步骤 2：文献综述与论文分析（获取层）
使用 **Academic Researcher** 完成：
- 审阅已收集的学术论文
- 开展系统性文献综述分析
- 识别研究主题、趋势和空白
- 梳理各论文间的逻辑关系和理论脉络
- 形成文献综述的整体框架

输出文献综述框架和论文关系图谱。

## 步骤 3：论文结构化深度拆解（分析层）
使用 **Paper Analyzer** 完成：
- 基于 12 个阅读要素深度拆解每篇论文
- 提取研究背景、研究问题、研究方法和理论框架
- 分析一致性发现和不一致性发现
- 评估研究贡献、研究不足和未来展望
- 将拆解结果保存为结构化 Excel 文件

输出论文深度拆解表和要素分析。

## 步骤 4：系统性中英文文献回顾（分析层）
使用 **Literature Reviewer Skill** 完成：
- 采用 8 阶段工作流进行系统性文献回顾
- 支持 CNKI、Web of Science、ScienceDirect 等数据库
- 无需 API 配置，通过浏览器自动化获取文献
- 中英文文献同步回顾和交叉分析
- 生成文献回顾的完整报告

输出系统性文献回顾报告。

## 步骤 5：综述框架与大纲生成（输出层）
使用 **Thesis Helper** 完成：
- 生成论文大纲和文献综述框架
- 撰写研究摘要和各章节概要
- 转换和规范引用格式
- 执行格式规范检查
- 准备答辩相关材料

输出综述大纲、框架和格式规范文档。

## 步骤 6：学术综述正文撰写（输出层）
使用 **academic-writing** 完成：
- 按学术规范撰写文献综述正文
- 包含引言、主题分析、批判性讨论和结论
- 严格遵守引用标准和学术写作规范
- 保持论述逻辑严密、语言专业准确
- 输出可直接提交的文献综述全文

## 最终输出
将以上步骤的结果整合为完整的文献综述包，交付以下文件：
1. **深度调研报告**：双轮调研、证据分级、APA 引用
2. **文献框架图谱**：主题梳理、趋势识别、研究空白
3. **论文拆解表**：12 要素分析、结构化 Excel
4. **系统性回顾报告**：中英文文献、8 阶段工作流
5. **综述大纲与框架**：章节结构、引用格式、格式规范
6. **综述正文**：学术写作、批判性讨论、可提交全文
