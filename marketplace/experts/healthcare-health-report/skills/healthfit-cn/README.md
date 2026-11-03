<div align="center">

# HealthFit.skill

> *「你的私人健康顾问矩阵，中西医融合，随时随地守护你的健康旅程」*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-4.0.0-brightgreen)](SKILL.md)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![Skills](https://img.shields.io/badge/skills.sh-Compatible-green)](https://skills.sh)
[![中西医融合](https://img.shields.io/badge/中西医-融合-red)](SKILL.md)

<br>

**HealthFit 为你打造 13 位专业顾问的健康专家矩阵——**
**运动教练按项目细分，营养师中西医并轨，中医顾问学科专精。**

<br>

运动教练矩阵覆盖 100+ 运动项目：跑步、游泳、力量、球类、武术、瑜伽、骑行……<br>
中医顾问矩阵涵盖体质辨识、养生功法（八段锦/五禽戏/六字诀）、妇科、内科……<br>
一个 Skill，你的完整健康生命周期伴侣。

[快速开始](#快速开始) · [专家矩阵](#专家矩阵) · [功能特性](#功能特性) · [安装方式](#安装方式) · [内容规范](#内容规范)

<br>

**其他语言 / Other Languages:**
[English](README_EN.md)

</div>

---

## 📖 什么是 HealthFit

HealthFit 是一个为 Claude（及其他 AI 工具）设计的健康管理 Skill，通过**专家矩阵**模式，将个人健康管理从单一助手升级为**13 位专业顾问的协作体系**：

- 🏃 **运动教练矩阵**（7 位）：每种运动项目都有对应的专业教练
- 🥗 **营养顾问矩阵**（5 位）：西医营养 + 中医体质辨识 + 养生功法 + 妇科 + 内科
- 📊 **数据分析师**（1 位）：周报、月报、趋势追踪、成就里程碑

---

## 🎯 专家矩阵

### 🏃 运动教练矩阵（7 位）

| 教练 | 专项 | 覆盖项目 |
|------|------|---------|
| Coach Lin | 田径/跑步 | 马拉松、5K/10K、越野跑、田径短跑/中长跑 |
| Coach Shui | 游泳 | 四种泳姿、健身游泳、开放水域、铁人三项游泳段 |
| Coach Alex | 力量/综合 | 深蹲硬拉卧推、健美、CrossFit、综合健身 |
| Coach Qiu | 球类运动 | 篮球、足球、网球、羽毛球、乒乓球等 |
| Coach Wu | 武术/搏击 | 拳击、泰拳、MMA、传统武术（竞技版）|
| Coach Rou | 柔韧/身心 | 瑜伽、普拉提、拉伸恢复、筋膜放松 |
| Coach Che | 耐力运动 | 自行车、骑行、铁人三项、皮划艇 |

> 📌 完整的 100+ 运动项目路由见 `references/sport_routing.md`

### 🥗 营养顾问矩阵（5 位）

| 顾问 | 专项 | 核心功能 |
|------|------|---------|
| Dr. Mei | 西医运动营养 | 热量目标、宏量营养素、运动补剂、体重管理 |
| Dr. Chen | 中医体质综合 | 九体质辨识、食疗方案、舌诊、节气养生 |
| Dr. Gong | 养生功法 | 八段锦、五禽戏、六字诀、易筋经、太极养生操 |
| Dr. Fang | 中医妇科 | 月经周期调理、产后恢复、痛经、PCOS 干预 |
| Dr. Nei | 中医内科 | 失眠调理、消化功能、慢性疲劳、亚健康 |

### 📊 数据分析（1 位）

| 分析师 | 核心功能 |
|--------|---------|
| Analyst Ray | 周报/月报、身体变化趋势、PR 最佳成绩、成就里程碑 |

---

## ✨ 功能特性

### 🔑 核心功能
- **智能路由**：根据用户描述的运动项目自动分配对应专业教练
- **双轨建档**：西医基础数据 + 中医体质辨识，建立完整健康画像
- **长期追踪**：本地数据持久化，支持周报/月报/趋势分析
- **快捷命令**：`/run`、`/swim`、`/eat`、`/weight`、`/pr` 等快速记录

### 🌿 中医特色功能
- **九体质辨识**：完整的中医体质评估与个性化调养方案
- **养生功法库**：八段锦、五禽戏、六字诀、易筋经完整教学
- **二十四节气**：按节气推送养生建议，天人合一
- **功法×体质矩阵**：根据体质推荐最适合的养生功法
- **月经周期运动方案**：四阶段差异化建议（月经期/卵泡期/排卵期/黄体期）

### 🔒 隐私保护
- 所有数据本地存储，无云端上传
- 性健康数据独立隔离文件，默认排除备份
- 用户随时可导出或完全清除数据

---

## 🚀 快速开始

### ⚡ 最快方式：npx 一键安装

```bash
npx skills add ChenChen913/healthfit
```

### 手动安装后，直接说：

```
帮我建立健康档案
```

### 方式 2：直接对话触发

以下任意说法均可触发 HealthFit：

```
今天跑了 5 公里，帮我记录
我想制定游泳训练计划
我的中医体质是什么？
帮我制定马拉松备赛计划
今天想练八段锦
本周训练总结
```

### 方式 3：快捷命令

```
/run 10K 52min         # 记录跑步
/swim 自由泳 1000m     # 记录游泳
/weight 68.5           # 记录体重
/pr 深蹲 90kg          # 记录个人最佳
/week                   # 本周总结
/tcm                    # 查看中医体质
/solar                  # 节气养生
/menu                   # 完整功能菜单
```

---

## 📦 安装方式

### ⚡ 方式一：npx 一键安装（推荐）

```bash
# 推荐方式
npx skills add ChenChen913/healthfit

# 指定安装到 Claude Code
npx skills add ChenChen913/healthfit -a claude-code

# 全局安装
npx skills add ChenChen913/healthfit -g
```

安装完成后，Skill 会自动配置到你的 Claude Code 环境，立即可用。

> 需要先安装 [Node.js](https://nodejs.org/)（v18+）。`npx` 会自动拉取最新版本，无需手动更新。

### 🔧 方式二：Claude Code 手动安装

```bash
git clone https://github.com/ChenChen913/healthfit ~/.claude/skills/healthfit
```

### 🛠 方式三：Cursor / Windsurf / Trae
将 `healthfit/` 文件夹放置于项目根目录，参考 [AGENTS.md](AGENTS.md) 进行配置。

### 📖 其他 AI 工具
详见 [AGENTS.md](AGENTS.md) — 涵盖 Cursor、Gemini CLI、OpenHands、OpenAI Codex 等配置。

---

## 🚨 内容规范

HealthFit 内置**内容规范层**，适用于所有角色：

- **性健康话题**：仅限于健康管理和运动优化目的，不涉及露骨内容
- **文明用语**：轻度不文明用语给予一次友好提醒，严重违规终止对话
- **医疗免责**：所有建议不构成医疗诊断，心血管疾病/术后恢复等请就医

---

## 📁 项目结构

```
healthfit/
├── SKILL.md                 # 系统核心配置
├── README.md                # 中文说明（本文件）
├── README_EN.md             # 英文说明
├── AGENTS.md                # 多 AI 工具适配
├── agents/                  # 13 位专家角色（7 教练 + 5 营养顾问 + 1 分析师）
├── references/              # 核心参考文档（17 个）
│   ├── sport_routing.md     # 100+ 运动项目路由表
│   ├── tcm_qigong_library.md# 养生功法完整库
│   └── ...
├── assets/                  # 资产（体测流程、舌诊指南、成就里程碑）
├── data/                    # 本地数据存储
└── scripts/                 # 工具脚本（备份/导出/数据库）
```

---

## 🤝 贡献与反馈

欢迎提交 Issue 或 PR：
- 新增运动项目路由
- 完善中医功法教学内容
- 增加新的营养顾问专项（如运动医学、肿瘤营养等）
- 多语言支持

---

## 📄 许可证

[MIT License](LICENSE) — 自由使用，欢迎二次开发。

---

<div align="center">

*HealthFit v4.0 — 专家矩阵，中西融合*<br>
*你的专属健康旅程伴侣*

[⭐ Star this repo](https://github.com/ChenChen913/healthfit) · [English Version](README_EN.md)

</div>
