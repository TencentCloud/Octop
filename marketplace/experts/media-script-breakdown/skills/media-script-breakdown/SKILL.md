---
name: media-script-breakdown
description: >-
  脚本拆解专家包。适用于脚本拆解、从专业四幕AI视频剧本与剧集拆分分镜脚本生成、电影视频剧本到分镜表格转换（镜号/ 景别/画面/人物/场景/音效）、
  短剧剧本角色塑造与剧情设计、到短视频分镜脚本撰写（黄金3秒/情绪钩子/镜头语言）、视频脚本分镜结构化输出与图谱管道式剧本生成管理的完整脚本拆解工作流、
  剧本创作等场景；也适用于用户明确要求调用「脚本拆解 / 脚本拆解专家包 / Script Breakdown」。
version: 1.0.0
metadata:
  author: SkillHub
  package_type: meta-skill
  display_name: 脚本拆解
  aliases:
    - 脚本拆解
    - 脚本拆解专家包
    - 脚本拆解技能包
    - Script Breakdown
    - media-script-breakdown
    - script-breakdown
orchestration:
  children:
    - seedance2-storyboard-generator
    - script-to-storyboard
    - short-drama-writer
    - ai-viral-team-script-writing
    - video-script-generator
    - movie
compatibility: SkillHub meta-skill, exportable to Claude Code / Codex markdown skill.
---
# 脚本拆解工作流

你现在要完成一项脚本拆解与分镜转化任务。你已安装以下 Skill，请按步骤串联使用：

## 步骤 1：四幕剧本与分镜脚本生成（获取层）
使用 **Seedance2-Storyboard-Generator** 完成：
- 从故事或文章中提取核心剧情线
- 生成专业四幕 AI 视频剧本结构
- 执行剧集拆分和资产提示生成
- 输出 Seedance 2.0 平台兼容的分镜脚本
- 包含角色设定、场景描述和镜头指令

输出四幕剧本和分镜脚本。

## 步骤 2：剧本到分镜表格转换（获取层）
使用 **Script to Storyboard** 完成：
- 将剧本文本解析为结构化分镜表格
- 输出标准分镜格式（镜号/景别/拍摄角度/画面内容）
- 标注出场人物、场景环境和音效要求
- 根据场景描述生成拍摄计划
- 提取视觉元素供后续制作参考

输出标准分镜表格和拍摄计划。

## 步骤 3：短剧剧本创作（分析层）
使用 **Short Drama Writer** 完成：
- 生成竖屏短剧和微短剧剧本
- 设计剧情结构和反转节点
- 塑造角色性格和人物关系
- 编写对白和场景描述
- 输出可直接拍摄的短剧脚本

输出短剧剧本和角色设定。

## 步骤 4：短视频分镜与情绪设计（分析层）
使用 **Ai Viral Team Script Writing** 完成：
- 设计黄金 3 秒开头方案（3 种以上）
- 撰写分镜脚本（镜头语言/场景氛围/角色动作/台词/BGM）
- 设计槽点埋梗与情绪钩子
- 规划结尾互动引导
- 推荐视频生成配置和模型版本

输出短视频分镜脚本和情绪设计方案。

## 步骤 5：视频脚本结构化输出（输出层）
使用 **Video Script Generator** 完成：
- 根据产品/主题/目标受众/时长生成完整脚本
- 输出结构化分镜（JSON/YAML 格式）
- 支持多种脚本模板（痛点-解决/反转剧情/before-after）
- 包含画面描述、口播文案和字幕提示
- 适配抖音、B站、YouTube 等多平台

输出结构化视频脚本和分镜数据。

## 步骤 6：影视项目与制作流程管理（输出层）
使用 **Movie** 完成：
- 支持多剧集连续生成和版本管理
- 通过图谱管理人物、场景、钩子的关联关系
- 执行 AI 质检 + 人工确认的双控机制
- 确保角色一致性和剧情连贯性
- 输出完整的剧本工程文件

## 最终输出
将以上步骤的结果整合为完整的脚本拆解包，交付以下文件：
1. **四幕剧本**：剧情结构、剧集拆分、分镜脚本、资产提示
2. **标准分镜表格**：镜号、景别、画面、人物、场景、音效
3. **短剧剧本**：角色设定、剧情设计、对白、场景描述
4. **短视频分镜**：黄金开头、情绪钩子、镜头语言、BGM 推荐
5. **结构化脚本数据**：JSON/YAML 分镜、多模板、多平台适配
6. **剧本工程文件**：图谱管理、多剧集连续、质检双控
