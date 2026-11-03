# novel-generator

**爽文小说生成器** — 一个 [Agent Skill](https://agentskills.io)，让 AI 代理根据用户提供的方向自动生成章节制爽文小说。

[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-compatible-blue)](https://agentskills.io)
[![ClawdHub](https://img.shields.io/badge/ClawdHub-published-green)](https://github.com/kimo/novel-generator)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 功能特性

- **智能提示词生成** — 用户只需提供一句话方向（如"都市修仙爽文"），自动补全为完整的创作提示词
- **分章节生成** — 逐章创作，每章 2000-3000 字，章章有爽点，层层递进
- **记忆系统** — 通过 `.learnings/` 记录角色、地点、情节，确保前后一致不穿帮
- **关键情节图解** — 自动生成人物关系图、势力分布图、等级体系图（Mermaid 格式）
- **失败记录** — 生成问题自动记录，持续优化创作质量
- **多题材支持** — 都市、修仙、玄幻、重生、系统流、末世等

## 快速开始

### 安装

**通过 ClawdHub（推荐）：**

```bash
clawdhub install novel-generator
```

**手动安装：**

```bash
git clone https://github.com/kimo/novel-generator.git ~/.openclaw/skills/novel-generator
```

**Cursor / Claude Code：**

将 `novel-generator/` 目录放入项目根目录的 `skills/` 文件夹中即可。

### 使用

1. 告诉 AI 你想写什么类型的小说：

   > "帮我写一个废柴少年获得炼丹系统后逆袭的修仙爽文"

2. AI 自动完善提示词，生成大纲，请你确认

3. 确认后逐章生成，每章输出为独立 md 文件

4. 角色、地点、情节自动记录，确保故事连贯

### 初始化新小说

```bash
./scripts/init-novel.sh 我的小说名 --clean
```

## 目录结构

```
novel-generator/
├── SKILL.md                    # 主文件：完整工作流和创作规范
├── assets/
│   ├── PROMPT-TEMPLATE.md      # 提示词生成模板
│   ├── CHAPTER-TEMPLATE.md     # 章节生成模板
│   └── LEARNINGS-TEMPLATE.md   # 记忆文件模板
├── .learnings/
│   ├── CHARACTERS.md           # 角色档案
│   ├── LOCATIONS.md            # 地点档案
│   ├── PLOT_POINTS.md          # 关键情节档案
│   ├── STORY_BIBLE.md          # 世界观设定
│   └── ERRORS.md               # 生成错误日志
├── references/
│   ├── prompt-guide.md         # 提示词完善指南
│   ├── plot-structures.md      # 爽文情节结构参考
│   └── examples.md             # 完整示例集
├── scripts/
│   └── init-novel.sh           # 初始化脚本
└── output/                     # 生成的章节输出目录
```

## 工作流

```
用户提供方向 → 自动完善提示词 → 生成大纲 → 逐章创作 → 输出 md 文件
                                              ↕
                                     .learnings/ 记忆系统
                                   （角色/地点/情节/世界观）
```

## 记忆系统

每次生成新章节前，AI 代理会自动读取记忆文件：

| 文件 | 作用 |
|------|------|
| `CHARACTERS.md` | 防止角色穿帮（已死复活、等级倒退） |
| `LOCATIONS.md` | 保持空间描写一致 |
| `PLOT_POINTS.md` | 管理伏笔的埋设与回收 |
| `STORY_BIBLE.md` | 守护世界观设定不自相矛盾 |
| `ERRORS.md` | 记录问题，避免重蹈覆辙 |

## 支持的题材

| 题材 | 典型元素 |
|------|---------|
| 都市 | 重生/系统/赘婿/装逼打脸 |
| 修仙 | 废柴逆袭/炼丹/宗门/越级挑战 |
| 玄幻 | 血脉觉醒/远古传承/神器 |
| 科幻 | 星际/机甲/基因改造 |
| 末世 | 丧尸/变异/生存/随身空间 |
| 游戏 | 网游/全息/副本/排行榜 |

## 兼容性

本技能遵循 [Agent Skills 规范](https://agentskills.io/specification)，兼容以下工具：

- Claude Code
- Cursor
- OpenAI Codex
- GitHub Copilot
- OpenClaw
- 其他支持 Agent Skills 的工具

## 灵感来源

记忆系统设计参考了 [self-improving-agent](https://github.com/peterskoett/self-improving-agent) 的 `.learnings/` 模式。

## 许可证

[MIT](LICENSE)
