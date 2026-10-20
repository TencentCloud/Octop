---
name: skill-creator
description: |
  创作或改进一个 Skill（包含可执行的、可复用的能力，由 ``SKILL.md`` 加可选的
  ``scripts/``、``references/`` 和资产文件组成）。
  在以下场景触发此技能：
    - 用户想把重复的工作流捕获为一个新 Skill
    - 优化现有 Skill 的提示词、描述或示例
    - 收紧触发条件措辞，让模型更可靠地调用该 Skill
    - 讨论 Skill 格式、frontmatter 或渐进式披露如何工作
  不要等用户说"skill-creator"原话——像"把它变成一个 skill"、"我们给这个做个可复用的东西"、
  "改进我的 skill" 或 "调整这个 skill 的描述" 这类短语都应该触发此技能。
metadata:
  octop:
    label:
      zh: "技能创作"
      en: "Skill Creator"
    summary:
      zh: "编写或改进可复用的 SKILL.md 技能包。"
      en: "Author or improve reusable SKILL.md skill packages."
  harness:
    emoji: "🧩"

---

# Skill 创建器

用于设计新 Skill 和迭代现有 Skill 的元技能。

Skill 是教会 Harness Agent 可复用能力的方式——写入工作区 skills 目录（优先 ``.octop/skills/``；若工作区没有 ``.octop`` 目录则用根目录 ``skills/``），agent 按需加载。

这是 Anthropic 原始 ``skill-creator`` recipe 的**库级**版本。它保留了核心创作循环（意图 → 起草 → 测试 → 迭代），去掉了 Anthropic 私有的工具链（``claude -p``、``eval-viewer``、``run_loop.py``、Cowork 特定行为）。如果你需要定量基准测试，可以自行接入这些工具——Skill 格式和创作循环并不依赖它们。

## 高层循环

1. 捕获意图。询问用户这个 Skill 应该实现什么、何时触发、输出长什么样。
2. 起草 ``SKILL.md``，包含 frontmatter 和简短正文。
3. 用加载了该 Skill 的 agent 跑几个真实的测试提示词，人工检查效果。
4. 根据观察到的结果编辑 Skill（主要是 description 和正文）。
5. 重复步骤 3–4，直到你和用户都满意。
6. 可选地，优化 description 的触发准确度（description 是模型决定是否查阅 Skill 的主要机制）。

## 文件结构

```
.octop/skills/<skill-name>/   # 优先；无 .octop 时用 skills/<skill-name>/
├── SKILL.md          # 必需：frontmatter + 正文
├── scripts/           # 可选：被 LLM 调用的辅助脚本
├── references/        # 可选：供 LLM 读取的参考文档
└── assets/           # 可选：图片、字体等静态资产
```

## SKILL.md 格式

````markdown
---
name: <slug-used-as-route-key>
description: |
  何时触发此技能的详细说明。用用户的语言写。
metadata:
  harness:
    emoji: "🎯"
  octop:
    label:
      zh: "示例技能"
      en: "Example Skill"
    summary:
      zh: "给 UI 卡片用的一句话简介。"
      en: "One-line card copy for the skills UI."
---

# <技能标题>

<使用说明、原则、示例>
````

`name` 和 `description` 仍是 Agent Skills 契约：`name` 是稳定 slug，`description` 是模型每轮看到的**触发**文案。不要为了适配卡片而缩短 `description`。

可选 UI 元数据（`metadata.octop.label.{zh,en}` 与 `metadata.octop.summary.{zh,en}`）只给目录和卡片用。新建**内置**技能应同时写上两种语言。`label` 要自然简短；`summary` 是一句话，且明显短于触发用的 `description`。emoji 放在 `metadata.harness`（Octop 专用技能可放在 `metadata.octop`）；不要把 emoji 复制到两个命名空间。

## 渐进式披露

Skill 只在需要时加载。把最关键的触发说明放在 `description` 中；把详细的用法、示例、排错指南放在正文里。

## 测试

边写边测：给你的 agent 发真实的提示词，观察它是否按预期触发和调用工具。
````

## 发布

Skill 可以通过 ``install-skill`` 技能打包分享，或直接提交到 octop-harness 仓库的 ``builtin/skills/`` 目录。
