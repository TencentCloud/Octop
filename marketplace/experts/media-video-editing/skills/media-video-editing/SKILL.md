---
name: media-video-editing
description: >-
  视频剪辑专家包。适用于视频剪辑、从AI对话式视频剪切合并与FFmpeg自动精彩片段提取字幕生成、
  自然语言驱动FFmpeg命令生成（剪辑/ 裁剪/转换/压缩）与多功能视频编辑（剪切/合并/格式转换/提取音频/添加字幕）、
  到自动生成视频脚本字幕标题与Remotion+React程序化视频创作的完整视频剪辑工作流、素材处理、智能剪辑、格式转换等场景；
  也适用于用户明确要求调用「视频剪辑 / 视频剪辑专家包 / Video Editing」。
version: 1.0.0
metadata:
  author: SkillHub
  package_type: meta-skill
  display_name: 视频剪辑
  aliases:
    - 视频剪辑
    - 视频剪辑专家包
    - 视频剪辑技能包
    - Video Editing
    - media-video-editing
    - video-editing
orchestration:
  children:
    - ai-video-clipper
    - video-clip-assistant
    - ffmpeg-video-editor
    - video-editor
    - ai-agentic-video-editor
    - remotion-video-toolkit
compatibility: SkillHub meta-skill, exportable to Claude Code / Codex markdown skill.
---
# 视频剪辑工作流

你现在要完成一项视频剪辑任务。你已安装以下 Skill，请按步骤串联使用：

## 步骤 1：AI 对话式视频剪辑（获取层）
使用 **AI视频剪辑Skill** 完成：
- 通过对话描述剪辑需求，AI 自动执行
- 剪切指定片段、合并多段素材
- 添加背景音乐和基础音效
- 快速完成粗剪和初步整理
- 输出初剪版本供后续精修

输出 AI 对话式初剪视频。

## 步骤 2：自动精彩片段提取（获取层）
使用 **视频自动剪辑助手** 完成：
- 基于 FFmpeg 自动提取视频精彩片段
- 生成字幕并烧录到视频
- 按时长裁剪制作短视频
- 支持多平台导出格式适配
- 生成视频摘要和关键片段索引

输出精彩片段和字幕烧录视频。

## 步骤 3：自然语言驱动 FFmpeg（分析层）
使用 **ffmpeg-video-editor** 完成：
- 将自然语言编辑需求转换为 FFmpeg 命令
- 执行专业级剪辑、裁剪、格式转换和压缩
- 修改视频宽高比、提取音频轨道
- 调整分辨率、码率和帧率参数
- 批量处理多个视频文件

输出 FFmpeg 处理后的专业级视频。

## 步骤 4：多功能视频编辑（分析层）
使用 **Video Editor** 完成：
- 使用 FFmpeg 执行综合视频编辑任务
- 支持剪切、合并、格式转换、提取音频
- 添加字幕、缩放、裁剪和调速
- 精细调整画面参数和音频参数
- 输出多种目标格式的成品视频

输出精编视频成品。

## 步骤 5：脚本字幕标题自动生成（输出层）
使用 **Ai Agentic Video Editor** 完成：
- 自动生成视频脚本和分镜文本
- 生成多语言字幕文件
- 创建吸引眼球的视频标题和封面文案
- 适配自媒体、UP 主等创作者需求
- 输出可直接发布的视频配套文本

输出视频脚本、字幕和标题文案。

## 步骤 6：程序化视频创作（输出层）
使用 **Remotion Video Toolkit** 完成：
- 使用 Remotion + React 进行程序化视频制作
- 实现精确的动画和时间控制
- 添加字幕、3D 效果、图表和文字特效
- 支持 CLI/Node.js/Lambda 等多种渲染方式
- 制作可复用的视频模板和组件

## 最终输出
将以上步骤的结果整合为完整的视频剪辑包，交付以下文件：
1. **AI 初剪视频**：对话式剪辑、片段合并、背景音乐
2. **精彩片段集**：自动提取、字幕烧录、多平台适配
3. **FFmpeg 专业处理**：格式转换、参数调优、批量处理
4. **精编成品视频**：综合编辑、音视频调整、多格式输出
5. **配套文本素材**：视频脚本、字幕文件、标题封面文案
6. **程序化视频模板**：Remotion 组件、动画特效、可复用模板
