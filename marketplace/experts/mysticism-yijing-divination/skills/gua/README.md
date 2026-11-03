# 易经起卦解卦 Skill / I Ching Divination Skill

[中文](#中文) | [English](#english)

---

<a id="中文"></a>

## 中文

### 简介

这是一个基于《周易》的起卦与解卦技能（Skill）。用户只需用自然语言提出问题，即可自动完成起卦、获取卦象，并结合联网检索给出针对用户问题的解卦结果。

### 功能特性

- **自动起卦**：根据用户问题与当前时间生成伪随机种子，模拟"三硬币法"（铜钱起卦）得出本卦与变卦
- **卦象可视化**：输出卦象图形（▅▅▅▅▅ / ▅▅ ▅▅），标注动爻（○ ×）
- **变爻识别**：自动识别老阳、老阴等变爻，生成对应的变卦
- **64 卦本地参考**：内置完整的六十四卦卦辞、象辞、爻辞与白话释义
- **联网校对**：在拿到卦名后联网检索，交叉验证卦义与爻辞
- **结构化解卦**：严格按照变爻数量遵循七种取辞规则，给出针对性解读

### 项目结构

```
gua-skill/
├── SKILL.md                        # Skill 主指令文件（定义工作流程与规则）
├── README.md                       # 本文件
├── scripts/
│   └── qi_gua.py                   # 起卦脚本（三硬币法模拟）
├── references/
│   ├── zhouyi-64-gua.md            # 六十四卦本地参考（卦辞、象辞、爻辞、白话）
│   ├── pre-divination-guidance.md  # 问卦前提醒要点
│   └── output-format.md            # 输出格式规范
└── agents/
    └── openai.yaml                 # OpenAI 兼容 Agent 配置
```

### 使用方法

#### 命令行起卦

```bash
python3 ./scripts/qi_gua.py "我最近是否适合换工作？"
```

输出包含：问题、起卦时间、本卦与变卦信息、卦象图形、六爻详情、上下卦与所属宫。

#### 作为 Skill 使用

将本项目作为 opencode skill 加载后，直接用自然语言提问即可。工作流程：

1. **问卦前提醒**：若用户要起卦，先转述注意事项，等待用户确认
2. **整理占问句**：将用户输入整理为简洁明确的占问句
3. **调用起卦脚本**：运行 `qi_gua.py` 获取卦象
4. **检索卦义**：先查本地参考，再联网校对补充
5. **解卦输出**：按变爻规则结合用户问题给出结构化解读

### 解卦规则（变爻取辞）

| 变爻数量 | 取用依据 |
|---------|---------|
| 0（静卦） | 本卦卦辞 |
| 1 | 该变爻的爻辞 |
| 2 | 两个变爻的爻辞，以上爻为主 |
| 3 | 本卦卦辞 + 变卦卦辞 |
| 4 | 两个静爻的爻辞，以下爻为主 |
| 5 | 变卦的静爻爻辞 |
| 6（全变） | 乾/坤用"用九/用六"，其他用变卦卦辞 |

### 技术细节

- 起卦种子由 `MD5(问题 + 时间戳)` 生成，同一问题在不同时间会产生不同卦象
- 每爻由三枚硬币（2 或 3）求和：6=老阴（变）、7=少阳、8=少阴、9=老阳（变）
- 卦象由下往上排列，对应初爻到上爻

---

<a id="english"></a>

## English

### Introduction

This is an I Ching (Yi Jing) divination skill. Users can ask questions in natural language, and the system will automatically generate hexagrams, retrieve relevant interpretations, and provide structured readings tailored to the user's question.

### Features

- **Automated Hexagram Generation**: Uses the question text and current timestamp to create a pseudo-random seed, simulating the traditional "three-coin method" to produce the primary and changed hexagrams
- **Visual Hexagram Display**: Outputs hexagram graphics using text symbols (▅▅▅▅▅ / ▅▅ ▅▅) with moving lines marked (○ ×)
- **Moving Line Detection**: Automatically identifies old yin and old yang as moving/changing lines and derives the resultant hexagram
- **Local 64-Hexagram Reference**: Built-in complete reference for all 64 hexagrams including judgments, image texts, line texts, and plain-language explanations
- **Online Verification**: Searches online after obtaining the hexagram name to cross-check interpretations
- **Structured Readings**: Follows the classic seven-fold moving-line rules to deliver targeted interpretations

### Project Structure

```
gua-skill/
├── SKILL.md                        # Main skill instruction file (workflow & rules)
├── README.md                       # This file
├── scripts/
│   └── qi_gua.py                   # Divination script (three-coin simulation)
├── references/
│   ├── zhouyi-64-gua.md            # Local 64-hexagram reference
│   ├── pre-divination-guidance.md  # Pre-divination guidance notes
│   └── output-format.md            # Output format specification
└── agents/
    └── openai.yaml                 # OpenAI-compatible agent configuration
```

### Usage

#### Command Line

```bash
python3 ./scripts/qi_gua.py "Is it a good time for me to change jobs?"
```

Output includes: the question, divination timestamp, primary and changed hexagram details, hexagram graphics, six-line details, upper/lower trigrams, and palace assignment.

#### As a Skill

Load this project as an opencode skill, then simply ask questions in natural language. The workflow:

1. **Pre-divination Guidance**: If the user intends to divine, share preparation tips and wait for confirmation
2. **Question Refinement**: Condense the user's input into a clear divination question
3. **Run Script**: Execute `qi_gua.py` to obtain the hexagram
4. **Retrieve Interpretations**: Check local references first, then verify online
5. **Reading Output**: Follow the moving-line rules and deliver a structured reading relevant to the user's question

### Divination Rules (Moving Line Selection)

| Moving Lines | Source for Reading |
|---|---|
| 0 (static) | Primary hexagram judgment |
| 1 | The moving line's text |
| 2 | Both moving lines' texts; upper line takes priority |
| 3 | Primary hexagram judgment + changed hexagram judgment |
| 4 | Two static lines' texts; lower line takes priority |
| 5 | Changed hexagram's static line text |
| 6 (all moving) | Qian/Kun use "Use of Nine / Use of Six"; others use changed hexagram judgment |

### Technical Details

- The divination seed is generated via `MD5(question + timestamp)`, so the same question at different times produces different hexagrams
- Each line is determined by the sum of three coins (2 or 3): 6 = old yin (moving), 7 = young yang, 8 = young yin, 9 = old yang (moving)
- Lines are arranged bottom to top, corresponding to the 1st through 6th positions
