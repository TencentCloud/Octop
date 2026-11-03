# 道传小六壬 AI 代理技能（xiaoliuren-skill）

为 AI 代理（DeepSeek Harness / Hermes / Cursor / Claude Code / OpenClaw / VS Code Copilot 等）提供专业级小六壬起卦、排盘与解卦能力的技能包。

## 特点

- **算法经过审核**：修正了网络上常见的五行归属错误（留连属土、小吉属水）
- **完整知识体系**：涵盖三种起卦方式、五行生克、六亲、死活六神、六步解卦法
- **即插即用**：`SKILL.md` 单文件包含全部核心知识，AI 代理加载即可使用
- **标准化输出**：提供排盘表和解卦的完整输出模板

## 文件结构

```
xiaoliuren-skill/
├── SKILL.md      # 主技能文件（含规范 frontmatter，代理读取即可获得全部能力）
├── examples.md   # 起卦示例与验证用例（7 组标准用例）
├── README.md     # 本说明文件
└── LICENSE       # MIT 许可证
```

## 快速开始

### DeepSeek Harness

DSH 会扫描以下技能根目录（一层深度的 `<name>/SKILL.md` 目录包或 `<name>.md` 平铺文件）：

| 优先级 | 目录 | 说明 |
| ------ | ---- | ---- |
| 项目级 | `<项目根>/.dsh/skills/` | 仅该项目会话可用 |
| 项目级 | `<项目根>/.agents/skills/` | 兼容共享 agent 配置 |
| 用户级 | `~/.dsh/skills/` | 所有会话可用（推荐） |
| 用户级 | `~/.agents/skills/` | 兼容共享 agent 配置 |

用户级安装（推荐，macOS / Linux）：

```bash
git clone https://github.com/tianmingwangluo/xiaoliuren-skill.git
mkdir -p ~/.dsh/skills/xiaoliuren-skill
cp xiaoliuren-skill/SKILL.md xiaoliuren-skill/examples.md ~/.dsh/skills/xiaoliuren-skill/
```

Windows PowerShell 等价命令：

```powershell
git clone https://github.com/tianmingwangluo/xiaoliuren-skill.git
New-Item -ItemType Directory -Force "$env:USERPROFILE\.dsh\skills\xiaoliuren-skill" | Out-Null
Copy-Item SKILL.md, examples.md "$env:USERPROFILE\.dsh\skills\xiaoliuren-skill\"
```

安装后无需重启 DSH，技能目录会热刷新：

- **自动调用**：会话中直接描述占卜需求（如"帮我用小六壬算一下今天的财运"），模型会自动加载本技能执行排盘解卦。
- **手动调用**：在输入框输入 `/xiaoliuren-divination` 可显式加载技能正文。
- **资源解析**：`SKILL.md` 正文引用的相对路径（如 `examples.md`）以技能目录为基准解析，模型会按需读取验证用例。

本技能的 frontmatter 同时兼容 DSH（`name`、`description`、`whenToUse`、`user-invocable`、`metadata`）与 Hermes（`name`、`description`、`version`、`author`、`license`、`metadata.hermes.tags`）规范，并保持与 Cursor / Claude Code 等代理的兼容。

### Hermes Agent

Hermes 的技能存放在 `~/.hermes/skills/`（若设置了 `HERMES_HOME` 环境变量则为 `$HERMES_HOME/skills/`）。本仓库 `SKILL.md` 位于根目录，推荐本地安装（完整保留 `examples.md`），macOS / Linux：

```bash
git clone https://github.com/tianmingwangluo/xiaoliuren-skill.git
mkdir -p "${HERMES_HOME:-~/.hermes}/skills/xiaoliuren-divination"
cp xiaoliuren-skill/SKILL.md xiaoliuren-skill/examples.md "${HERMES_HOME:-~/.hermes}/skills/xiaoliuren-divination/"
```

Windows PowerShell 等价命令：

```powershell
git clone https://github.com/tianmingwangluo/xiaoliuren-skill.git
$h = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { "$env:USERPROFILE\.hermes" }
New-Item -ItemType Directory -Force "$h\skills\xiaoliuren-divination" | Out-Null
Copy-Item SKILL.md, examples.md "$h\skills\xiaoliuren-divination\"
```

也可从 GitHub 直接安装（会经过 Hermes 安全扫描；仅下载 `SKILL.md`，不含 `examples.md`）：

```bash
hermes skills install https://raw.githubusercontent.com/tianmingwangluo/xiaoliuren-skill/main/SKILL.md
```

安装后：

- **自动调用**：描述占卜需求（如"帮我用小六壬算一下今天的财运"），Hermes 会根据 `description` 自动加载本技能。
- **手动调用**：输入 `/xiaoliuren-divination` 可显式加载技能正文。
- **标签检索**：已提供 `metadata.hermes.tags`（占卜、小六壬、术数、传统文化），便于在 Skills Hub 检索。

## 其他 AI 代理

### Cursor / VS Code Copilot

将 `xiaoliuren-skill` 文件夹放入项目的 `.github/skills/`、`.agents/skills/` 或 `.claude/skills/` 目录下。AI 代理在用户请求小六壬占卜时会自动调用。

### Claude Code

将 `SKILL.md` 的内容作为系统提示或工具说明提供给 Claude。

### OpenClaw / 其他 AI 代理

将 `SKILL.md` 加载为知识库或技能文件即可。

### 通用方式

直接将 `SKILL.md` 的内容粘贴到任何 AI 对话的系统提示中，即可赋予 AI 专业的小六壬起卦能力。

## 使用示例

- "帮我用小六壬算一下今天的财运，数字 3、5、7"
- "用农历正月初五卯时起卦，看我这次出行顺不顺利"
- "测感情：3 6 9，帮我排盘解卦"

> 心诚则灵，一事不二占：同一件事不宜短时间内反复占问。

## 核心校正说明

本技能基于道传小六壬体系，与传统/网络版本的关键差异：

| 宫位 | 道传（本技能·正确） | 网络常见（错误） |
|------|---------------------|-----------------|
| 留连 | **土** | 水 |
| 小吉 | **水** | 土 |

## 来源

来自 [道传小六壬在线排盘](https://www.xiao6ren.com) 项目，算法与数据经过系统性整理审核。
