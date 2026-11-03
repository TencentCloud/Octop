---
version: "2.0.0"
name: Error Analysis
description: "错题分析助手。分析错误原因、知识点定位、举一反三出变式题。. Use when you need error analysis capabilities. Triggers on: error analysis."
  错题分析助手。错题归类、知识点定位、薄弱环节分析、复习建议。Error analysis for study with categorization, knowledge gap identification. 错题本、考试复盘、学习分析。Use when analyzing exam mistakes.
author: BytesAgain
homepage: https://bytesagain.com
source: https://github.com/bytesagain/ai-skills
---

# error-analysis

错题分析助手。分析错误原因、知识点定位、举一反三出变式题。

## Commands

All commands via `scripts/error.sh`:

| Command | Description |
|---------|-------------|
| `error.sh analyze "题目" "错误答案" "正确答案"` | 分析错题原因，定位知识点 |
| `error.sh knowledge "知识点"` | 知识点详细解析 |
| `error.sh similar "题目类型"` | 生成变式练习题 |
| `error.sh summary` | 错题统计与薄弱点分析 |
| `error.sh help` | 显示帮助信息 |

## Usage

```bash
bash scripts/error.sh analyze "求x^2+2x+1=0的解" "x=1" "x=-1"
bash scripts/error.sh knowledge "一元二次方程"
bash scripts/error.sh similar "函数求导"
bash scripts/error.sh summary
```

## Notes

- Python 3.6+ compatible
- No external dependencies
- 错题记录保存在 `data/errors.json`
---
💬 Feedback & Feature Requests: https://bytesagain.com/feedback
Powered by BytesAgain | bytesagain.com
