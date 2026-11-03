# AGENTS.md — HealthFit Skill 多 AI 工具适配配置

> 本文件定义 HealthFit Skill 在不同 AI 工具中的配置方式，确保跨工具一致性体验。

---

## 概览

HealthFit Skill 的核心逻辑在 `SKILL.md` 中定义。不同 AI 工具在加载 Skill 的方式上存在差异，本文件提供各工具的具体配置指引。

---

## Claude Code（推荐，功能完整）

**安装方式：**
```bash
# 方式 1：直接克隆到 skills 目录
git clone https://github.com/ChenChen913/healthfit ~/.claude/skills/healthfit

# 方式 2：使用 skills.sh（如已安装）
skills install healthfit
```

**配置文件（~/.claude/CLAUDE.md 或项目 CLAUDE.md）：**
```markdown
## Active Skills
- healthfit: 个人健康管理，当用户涉及运动、饮食、中医体质话题时激活
```

**特性支持：**
- ✅ 完整的文件读写（profile.json、workout_log.txt 等）
- ✅ Python 脚本执行（backup.py、export.py 等）
- ✅ SQLite 数据库读写（周报/月报功能）
- ✅ 所有 13 个专家角色完整路由

---

## Cursor（代码编辑器中使用）

**安装方式：**
将 `healthfit/` 文件夹放置于项目根目录或 `~/.cursor/skills/` 目录。

**`.cursorrules` 配置片段：**
```
You have access to the HealthFit skill located in ./healthfit/.
When the user mentions fitness, nutrition, TCM constitution, exercise logging,
or health management, load SKILL.md and follow its routing table.

Key behaviors:
- Route sports questions to the correct coach agent in ./healthfit/agents/
- Content moderation layer applies at all times (see SKILL.md)
- Data storage path: ./healthfit/data/
```

**特性支持：**
- ✅ 文件读写（需项目内路径）
- ✅ 专家角色路由
- ⚠️ Python 脚本需手动执行
- ❌ SQLite 查询功能受限

---

## Windsurf / Trae

**配置方式：** 与 Cursor 类似，将以下内容加入全局规则或项目规则：

```
HealthFit Skill is available at ./healthfit/SKILL.md.
Load it when health, fitness, nutrition, or TCM topics arise.
Follow the expert matrix routing defined in SKILL.md.
Enforce content moderation layer at all times.
Data path: ./healthfit/data/
```

---

## OpenHands（OpenDevin）

**配置文件（`.openhands/config.toml`）：**
```toml
[agent]
system_prompt_suffix = """
You have access to HealthFit health management skill.
Skill location: ./healthfit/SKILL.md
Activate when: exercise, diet, nutrition, TCM, health tracking topics
Follow expert routing table in SKILL.md.
Content moderation applies to sexual health discussions.
"""
```

---

## Gemini CLI

**配置方式（`~/.gemini/config.yaml`）：**
```yaml
system_instructions:
  - |
    HealthFit skill is available at ./healthfit/SKILL.md.
    Trigger on: fitness, nutrition, exercise, TCM, health management requests.
    Load the appropriate agent file from ./healthfit/agents/ based on the routing table.
    Enforce content moderation layer (no explicit sexual content, maintain civility).
```

---

## OpenAI Codex / ChatGPT（自定义 GPT）

**System Prompt 片段：**
```
You are HealthFit, a personal health management system with a matrix of expert advisors.
Core configuration is in [SKILL.md content pasted here].

Expert routing:
- Athletics/Running → Coach Lin
- Swimming → Coach Shui  
- Strength/General → Coach Alex
- Ball Sports → Coach Qiu
- Martial Arts → Coach Wu
- Flexibility → Coach Rou
- Endurance → Coach Che
- Western Nutrition → Dr. Mei
- TCM Constitution → Dr. Chen
- Qigong/Exercises → Dr. Gong
- TCM Gynecology → Dr. Fang
- TCM Internal → Dr. Nei
- Data Analysis → Analyst Ray

Content Moderation: Sexual health discussions are limited to health optimization only.
No explicit content. Maintain civility in all interactions.
```

---

## Claude.ai（Web / App）

**Skill 使用方式：**
在对话开始时发送：
```
请加载 HealthFit Skill。档案路径：[你的数据路径]
```

或直接触发：
```
帮我建立健康档案
今天跑了 5 公里
我的中医体质是什么
```

**特性支持：**
- ✅ 所有专家角色对话功能
- ⚠️ 文件持久化依赖 claude.ai 的 Storage API 或 Projects 功能
- ❌ Python 脚本需要 Claude Code 才能执行

---

## 通用配置原则

无论在哪个工具中使用，以下配置始终有效：

1. **内容规范优先级最高** — 性健康话题限于健康优化，文明用语警告机制
2. **专家路由必须遵守** — 不同运动项目路由到对应教练，不越界
3. **医疗免责声明** — 所有建议不构成医疗诊断
4. **隐私数据隔离** — 性健康数据独立存储，默认排除备份

---

## 版本兼容性

| 工具 | 最低版本要求 | 完整功能支持 |
|------|------------|------------|
| Claude Code | 任意版本 | ✅ 完整支持 |
| Cursor | 0.40+ | ⚠️ 部分支持（无脚本执行）|
| Windsurf / Trae | 最新版 | ⚠️ 部分支持 |
| Gemini CLI | 1.0+ | ⚠️ 部分支持 |
| OpenHands | 0.9+ | ✅ 较完整支持 |

---

*AGENTS.md — HealthFit v4.0 | 跨平台健康管理，随处可用*
