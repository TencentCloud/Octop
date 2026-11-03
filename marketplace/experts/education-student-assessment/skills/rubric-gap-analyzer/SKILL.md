---
name: rubric-gap-analyzer
description: 读取评分标准、作业要求或评估rubric，分析当前草稿的差距并给出提分计划。
metadata: {"openclaw":{"emoji":"📏","requires":{"bins":["node","pbpaste"]}}}
---

# Rubric Gap Analyzer

这是一个专门用于“评分标准对照分析”的 skill。

## 主要用途

当用户复制了以下内容时：
- 课程论文评分标准
- 作业 rubric
- 答辩评分表
- 项目评分维度
- 竞赛评审标准
- 投稿评审维度说明

你需要帮助用户：
1. 提取评分维度
2. 判断关键得分项
3. 识别当前草稿缺什么
4. 给出最高收益的修改顺序
5. 输出提分计划

## 调用方式

当用户说：
- 读取剪贴板里的评分标准帮我分析
- 用这个 rubric 帮我看看还差什么
- 根据评分细则给我提分建议
- 帮我按 rubric 改作业

你应运行：

```bash
node {baseDir}/scripts/read_clipboard.mjs