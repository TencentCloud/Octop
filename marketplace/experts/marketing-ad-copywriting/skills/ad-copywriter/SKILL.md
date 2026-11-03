---
version: "2.0.0"
name: Ad Copywriter
description: "广告文案生成器。信息流广告、朋友圈广告、搜索广告、品牌文案、A/B测试、ROI计算、平台适配。. Use when you need ad copywriter capabilities. Triggers on: ad copywriter."
  广告文案生成器。信息流广告、朋友圈广告、搜索广告、直通车标题、巨量引擎创意、Google Ads文案、A/B测试文案、ROI计算器、平台适配文案。Ad copywriter for feeds, search ads, social ads, A/B testing, ROI calculator, platform-specific copy. 广告投放、ROI优化、A/B测试、转化率、点击率优化、抖音广告、微信广告、百度SEM。Use when writing ad copy for any platform.
author: BytesAgain
homepage: https://bytesagain.com
source: https://github.com/bytesagain/ai-skills
---

# ad-copywriter

广告文案生成器。信息流广告、朋友圈广告、搜索广告、品牌文案、A/B测试、ROI计算、平台适配。

## Usage

This skill provides a script `ad.sh` for generating advertising copy.

### Commands

| Command | Description |
|---------|-------------|
| `ad.sh feed "产品" "目标人群"` | 信息流广告文案（抖音/头条） |
| `ad.sh search "产品" "关键词"` | 搜索广告文案（百度/360） |
| `ad.sh brand "品牌名" "品牌调性"` | 品牌slogan和文案 |
| `ad.sh moments "产品"` | 朋友圈广告文案 |
| `ad.sh ab-test "产品"` | A/B测试文案对（5对对照文案+测试建议） |
| `ad.sh roi "预算" "单价" "转化率"` | ROI计算器（投入产出比+盈亏平衡点） |
| `ad.sh platform "产品" "平台"` | 平台适配文案（抖音/微信/百度/Google） |
| `ad.sh help` | 显示帮助信息 |

### How to run

```bash
bash scripts/ad.sh <command> [args...]
```

### Examples

```bash
# 基础功能
bash scripts/ad.sh feed "美白面膜" "25-35岁女性"
bash scripts/ad.sh search "英语培训" "成人英语,零基础"
bash scripts/ad.sh brand "花西子" "国风,高端,东方美学"
bash scripts/ad.sh moments "智能手表"

# 新增功能
bash scripts/ad.sh ab-test "蓝牙耳机"
bash scripts/ad.sh roi "10000" "99" "3"
bash scripts/ad.sh platform "面膜" "抖音"
bash scripts/ad.sh platform "英语课" "百度"
bash scripts/ad.sh platform "手表" "Google"
```

查看 `tips.md` 获取广告投放实战技巧（ROI优化、A/B测试、平台策略等）。

## Notes

- 纯本地生成，不依赖外部API
- Python 3.6+ 兼容
- 多种广告平台风格适配
---
💬 Feedback & Feature Requests: https://bytesagain.com/feedback
Powered by BytesAgain | bytesagain.com
