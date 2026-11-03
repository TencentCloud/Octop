<div align="center">

# HealthFit.skill

> *"Your personal health advisor matrix — East meets West, anytime, anywhere"*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-4.0.0-brightgreen)](SKILL.md)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![Skills](https://img.shields.io/badge/skills.sh-Compatible-green)](https://skills.sh)
[![TCM+Western](https://img.shields.io/badge/TCM%2BWestern-Integrated-red)](SKILL.md)

<br>

**HealthFit builds a matrix of 13 specialized advisors for your health journey —**
**Sports coaches by discipline, nutrition experts bridging East and West medicine.**

<br>

Sports coach matrix covers 100+ disciplines: running, swimming, strength, ball sports, martial arts, yoga, cycling…<br>
TCM advisor matrix covers constitution diagnosis, qigong (Baduanjin/Wuqinxi/Liuzijue), gynecology, internal medicine…<br>
One skill, your complete lifelong health companion.

[Quick Start](#quick-start) · [Expert Matrix](#expert-matrix) · [Features](#features) · [Installation](#installation) · [Content Policy](#content-policy)

<br>

**其他语言 / Other Languages:**
[中文](README.md)

</div>

---

## 📖 What is HealthFit

HealthFit is a health management Skill designed for Claude (and other AI tools). Through an **Expert Matrix** architecture, it elevates personal health management from a single chatbot to a **13-expert collaborative system**:

- 🏃 **Sports Coach Matrix** (7 coaches): A specialist for every sport
- 🥗 **Nutrition Advisor Matrix** (5 advisors): Western nutrition + TCM constitution + Qigong + Gynecology + Internal Medicine
- 📊 **Data Analyst** (1 analyst): Weekly/monthly reports, trend tracking, achievement milestones

---

## 🎯 Expert Matrix

### 🏃 Sports Coach Matrix (7 Coaches)

| Coach | Specialty | Disciplines Covered |
|-------|-----------|-------------------|
| Coach Lin | Athletics / Running | Marathon, 5K/10K, trail running, track & field |
| Coach Shui | Swimming | All 4 strokes, fitness swimming, open water, triathlon swim |
| Coach Alex | Strength / General | Squat/deadlift/bench, bodybuilding, CrossFit, general fitness |
| Coach Qiu | Ball Sports | Basketball, soccer, tennis, badminton, table tennis, etc. |
| Coach Wu | Martial Arts / Combat | Boxing, Muay Thai, MMA, traditional martial arts (competitive) |
| Coach Rou | Flexibility / Mind-Body | Yoga, Pilates, stretching, fascia release |
| Coach Che | Endurance Sports | Cycling, triathlon, kayaking, rowing |

> 📌 Full routing for 100+ sports → `references/sport_routing.md`

### 🥗 Nutrition Advisor Matrix (5 Advisors)

| Advisor | Specialty | Core Functions |
|---------|-----------|---------------|
| Dr. Mei | Western Sports Nutrition | Calorie targets, macros, supplements, weight management |
| Dr. Chen | TCM Constitution (General) | 9-constitution diagnosis, food therapy, tongue examination, seasonal wellness |
| Dr. Gong | Qigong & Health Exercises | Baduanjin, Wuqinxi, Liuzijue, Yijinjing, Taiji health exercises |
| Dr. Fang | TCM Gynecology | Menstrual cycle optimization, postpartum recovery, dysmenorrhea, PCOS |
| Dr. Nei | TCM Internal Medicine | Insomnia, digestion, chronic fatigue, sub-health |

### 📊 Data Analysis (1 Analyst)

| Analyst | Core Functions |
|---------|---------------|
| Analyst Ray | Weekly/monthly reports, body change trends, PR records, achievement milestones |

---

## ✨ Features

### 🔑 Core Features
- **Smart Routing**: Automatically assigns the right specialist based on your sport/topic
- **Dual-Track Profiling**: Western health metrics + TCM constitution assessment
- **Long-term Tracking**: Local data persistence, weekly/monthly/trend analysis
- **Quick Commands**: `/run`, `/swim`, `/eat`, `/weight`, `/pr` for fast logging

### 🌿 TCM-Specific Features
- **9-Constitution Diagnosis**: Full TCM body type assessment with personalized care plans
- **Qigong Library**: Complete Baduanjin, Wuqinxi, Liuzijue, Yijinjing instructions
- **24 Solar Terms**: Seasonal wellness recommendations aligned with nature
- **Qigong × Constitution Matrix**: Recommends optimal exercises for your body type
- **Menstrual Cycle Exercise Plans**: 4-phase differentiated guidance

### 🔒 Privacy Protection
- All data stored locally — no cloud upload
- Sexual health data isolated in a separate file, excluded from backups by default
- Export or fully reset your data at any time

---

## 🚀 Quick Start

### ⚡ Fastest: npx One-Line Install

```bash
npx skills add ChenChen913/healthfit
```

### Then just say:

```
Help me create my health profile
```

### Option 2: Direct Conversation Triggers

Any of these will activate HealthFit:

```
I ran 5km today, log it for me
I want a swimming training plan
What is my TCM body constitution?
Help me train for a marathon
I want to practice Baduanjin today
Weekly training summary
```

### Option 3: Quick Commands

```
/run 10K 52min          # Log a run
/swim freestyle 1000m   # Log a swim
/weight 68.5            # Log weight
/pr squat 90kg          # Log a personal record
/week                    # Weekly summary
/tcm                     # View TCM constitution
/solar                   # Seasonal wellness tips
/menu                    # Full feature menu
```

---

## 📦 Installation

### ⚡ Option 1: npx One-Line Install (Recommended)

```bash
# Recommended
npx skills add ChenChen913/healthfit

# Install specifically for Claude Code
npx skills add ChenChen913/healthfit -a claude-code

# Global install
npx skills add ChenChen913/healthfit -g
```

The Skill is automatically configured for your Claude Code environment — no manual setup needed.

> Requires [Node.js](https://nodejs.org/) (v18+). `npx` always fetches the latest version automatically.

### 🔧 Option 2: Claude Code Manual Install
```bash
git clone https://github.com/ChenChen913/healthfit ~/.claude/skills/healthfit
```

### 🛠 Option 3: Cursor / Windsurf / Trae
Place the `healthfit/` folder in your project root directory. See [AGENTS.md](AGENTS.md) for configuration.

### 📖 Other AI Tools
See [AGENTS.md](AGENTS.md) — covers Cursor, Gemini CLI, OpenHands, OpenAI Codex, and more.

---

## 🚨 Content Policy

HealthFit has a built-in **Content Moderation Layer** applied to all advisors:

- **Sexual Health Topics**: Limited to health optimization only. No explicit content.
- **Civility**: One friendly reminder for mild language violations; serious violations end the conversation.
- **Medical Disclaimer**: All suggestions are not medical diagnoses. Consult a doctor for cardiovascular conditions, post-surgical recovery, and similar situations.

---

## 📁 Project Structure

```
healthfit/
├── SKILL.md                 # System core configuration
├── README.md                # Chinese documentation
├── README_EN.md             # English documentation (this file)
├── AGENTS.md                # Multi-AI tool configuration
├── agents/                  # 13 expert roles
│   ├── coach_athletics.md   # Track & field / Running
│   ├── coach_swim.md        # Swimming
│   ├── coach_alex.md        # Strength / General fitness
│   ├── coach_team.md        # Ball sports
│   ├── coach_martial.md     # Martial arts / Combat
│   ├── coach_flexibility.md # Flexibility / Mind-body
│   ├── coach_endurance.md   # Endurance sports
│   ├── dr_mei.md            # Western nutrition
│   ├── dr_chen.md           # TCM constitution
│   ├── dr_qigong.md         # Qigong / Health exercises
│   ├── dr_tcm_gynecology.md # TCM gynecology
│   ├── dr_tcm_internal.md   # TCM internal medicine
│   └── analyst_ray.md       # Data analyst
├── references/              # Core reference documents (17 files)
│   ├── sport_routing.md     # 100+ sport routing table
│   ├── tcm_qigong_library.md# Qigong complete library
│   └── ...
├── assets/                  # Fitness baseline test, tongue exam guide, etc.
├── data/                    # Local data storage
└── scripts/                 # Utility scripts (backup/export/database)
```

---

## 🤝 Contributing

Issues and PRs are welcome:
- Add new sport routing entries
- Expand TCM exercise instructions
- Add new nutrition specialties
- Multilingual support

---

## 📄 License

[MIT License](LICENSE) — Free to use, open to extend.

---

<div align="center">

*HealthFit v4.0 — Expert Matrix, East-West Integration*<br>
*Your dedicated health journey companion*

[⭐ Star this repo](https://github.com/ChenChen913/healthfit) · [中文版](README.md)

</div>
