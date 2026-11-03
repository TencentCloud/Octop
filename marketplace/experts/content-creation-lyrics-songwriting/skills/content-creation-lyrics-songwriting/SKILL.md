---
name: content-creation-lyrics-songwriting
description: >-
  歌词创作专家包。适用于歌词创作、Suno 浏览器主驱、作词方法论、元标签专家、风格仿写、情感弧线、MV 流水线等场景；
  也适用于用户明确要求调用「歌词创作 / 歌词创作专家包 / lyrics-songwriting」。
version: 1.0.0
metadata:
  author: SkillHub
  package_type: meta-skill
  display_name: 歌词创作
  aliases:
    - 歌词创作
    - 歌词创作专家包
    - 歌词创作技能包
    - content-creation-lyrics-songwriting
    - lyrics-songwriting
orchestration:
  children:
    - suno-browser-songmaking
    - acestep-songwriting
    - suno-music-composer
    - suno-poetry-music-creator
    - insight-song
    - songwriting-and-ai-music
compatibility: SkillHub meta-skill, exportable to Claude Code / Codex markdown skill.
---
# 歌词创作工作流

你现在要完成一项歌词创作并落地为歌曲/MV 的任务（含主歌副歌结构、押韵、情绪曲线、风格仿写、Suno 生成、MV 视听输出）。你已安装以下 Skill，请按步骤串联使用：

## 步骤 1：作词专业方法论与歌曲规划（处理层）
使用 **Acestep Songwriting** 完成：
- 与用户确认歌曲主题、目标受众、流派（流行/民谣/电音/说唱/古风等）
- 规划歌曲结构：Verse / Pre-Chorus / Chorus / Bridge / Outro
- 选择 BPM、调式（大调/小调）、时长、节奏型
- 给出押韵方案（句尾韵 / 转韵 / 内韵）与主歌副歌反差设计

输出歌曲规划文档（主题 + 流派 + 结构 + BPM + 调式 + 押韵方案）。

## 步骤 2：情感弧线作词（处理层）
使用 **Insight Song** 在步骤 1 基础上完成：
- 把歌曲主题转化为情感弧线（如：失落 → 挣扎 → 顿悟 → 释怀）
- 按情感弧线分段写出每个段落的歌词初稿
- 同步输出每段对应的风格标签（情绪强度、主导乐器、人声处理建议）

输出含情感弧线的歌词初稿 + 段落风格标签。

## 步骤 3：参考歌曲风格仿写（处理层）
若用户希望仿写某首参考歌曲风格，使用 **Suno Poetry Music Creator** 完成：
- 输入参考歌曲（链接/标题/描述）
- 提取参考的风格、情绪基调、和声进行、结构走向
- 把步骤 2 的歌词按参考风格做智能优化（保留情感弧线，调整字数/句式/用词）

输出风格仿写版歌词。

## 步骤 4：Suno 元标签深度调优（处理层）
使用 **Suno Music Composer** 把歌词包装成可被 Suno 高质量生成的 prompt：
- 套用 171+ 元标签速查表（流派、情绪、人声特征、乐器、混音风格、年代感等）
- 走"骨架（结构标签）+ 血肉（情绪/乐器/人声细节）"协同体系
- 输出最终可粘贴到 Suno 的歌词文本 + Style of Music prompt

输出 Suno 就绪的歌词 + Style prompt。

## 步骤 5：Suno 浏览器自动化生成歌曲（处理层）
使用 **Suno Browser Songmaking** 走免 Key 浏览器路径：
- 自动化打开 Suno 网页，填入步骤 4 的歌词与 Style prompt
- 选择 Persona 或自定义模式生成
- 拉回多版本生成结果，由用户/AI 选出最佳版本
- 必要时基于反馈做局部修改重生成

输出 Suno 生成的多版本歌曲音频 + 选定的最佳版本。

## 步骤 6：完整 MV 视听输出（输出层）
使用 **MV Pipeline** 把歌曲落地成完整 MV：
- 用 stable-ts 做歌词与音频对齐（精确到字/词级时间戳）
- 用 Veo 3.1 / Google Flow 按歌词意象生成视频片段
- 用 Remotion 做剪辑：字幕条、画面切换、特效、字幕动画
- 自动上传到 YouTube（可选）

输出完整 MV 视频文件 + 上传链接（按需）。

## 最终输出
将以上步骤的结果整合为完整的歌词创作与歌曲落地成果包，交付以下文件：
1. **歌曲规划**：主题、流派、结构、BPM、调式、押韵方案
2. **歌词稿**：含情感弧线 + 段落风格标签 + 风格仿写版（按需）
3. **Suno 就绪 prompt**：歌词 + Style of Music prompt（含元标签）
4. **歌曲音频**：Suno 生成的多版本 + 最佳版本
5. **完整 MV**（按需）：含字幕与对齐的 MV 视频 + YouTube 上传链接
