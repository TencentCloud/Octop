"""
行业分析工具 - 整合多数据源进行行业大盘分析
用法：python analyze_industry.py --industry "护肤品" --brand "XX品牌" --output report.md
"""

import argparse
import json
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# 所有爬虫脚本与本脚本同处 scripts/ 目录
SCRIPTS_DIR = Path(__file__).parent


def fetch_platform_data(keyword: str, platform: str, limit: int = 200) -> list:
    """调用同目录爬虫脚本获取平台数据"""
    script_map = {
        "douyin": SCRIPTS_DIR / "fetch_douyin.py",
        "xiaohongshu": SCRIPTS_DIR / "fetch_xiaohongshu.py",
        "weibo": SCRIPTS_DIR / "fetch_weibo.py",
    }

    script = script_map.get(platform)
    if not script or not script.exists():
        print(f"  ⚠️  {platform} 爬虫脚本未找到")
        return []

    try:
        result = subprocess.run(
            [sys.executable, str(script),
             "--keyword", keyword,
             "--limit", str(limit),
             "--sort", "hot",
             "--json"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            print(f"  ✅ {platform} 获取 {len(data)} 条数据")
            return data
    except Exception as e:
        print(f"  ❌ {platform} 获取失败: {e}")

    return []


def extract_keywords_from_content(content_list: list) -> dict:
    """从内容中提取高频关键词"""
    word_freq = {}
    for item in content_list:
        title = item.get("title", "") + " " + item.get("content", "")
        # 简单分词（实际应使用 jieba）
        words = [w.strip() for w in title.split() if len(w.strip()) > 1]
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1

    # 按频次排序，返回 TOP30
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return dict(sorted_words[:30])


def calculate_industry_metrics(data_by_platform: dict) -> dict:
    """计算行业指标"""
    total_items = sum(len(v) for v in data_by_platform.values())
    total_interactions = sum(
        item.get("likes", 0) + item.get("comments", 0) + item.get("shares", 0)
        for items in data_by_platform.values()
        for item in items
    )

    # 找爆款内容（播放量/点赞超过均值3倍）
    all_play_counts = [
        item.get("play_count", 0) or item.get("likes", 0)
        for items in data_by_platform.values()
        for item in items
    ]
    avg_play = sum(all_play_counts) / len(all_play_counts) if all_play_counts else 0

    viral_items = []
    for platform, items in data_by_platform.items():
        for item in items:
            count = item.get("play_count", 0) or item.get("likes", 0)
            if count > avg_play * 3:
                viral_items.append({**item, "platform": platform})

    viral_items.sort(key=lambda x: x.get("play_count", 0) or x.get("likes", 0), reverse=True)

    return {
        "total_content": total_items,
        "total_interactions": total_interactions,
        "avg_interaction_per_content": total_interactions / total_items if total_items else 0,
        "viral_count": len(viral_items),
        "top_viral": viral_items[:10],
    }


def generate_report(industry: str, brand: str, data_by_platform: dict,
                    metrics: dict, keywords: dict) -> str:
    """生成行业分析报告"""

    report_date = datetime.now().strftime("%Y-%m-%d")
    platforms = list(data_by_platform.keys())
    top_keywords = list(keywords.items())[:15]

    # 爆款内容列表
    viral_section = ""
    for item in metrics["top_viral"][:5]:
        platform = item.get("platform", "")
        title = item.get("title", "无标题")[:50]
        count = item.get("play_count", item.get("likes", 0))
        viral_section += f"| {title} | {platform} | {count:,} |\n"

    keyword_section = "\n".join([f"- **{w}**：出现 {c} 次" for w, c in top_keywords])

    report = f"""# {industry} 行业分析报告

**品牌**: {brand}  
**分析日期**: {report_date}  
**分析平台**: {', '.join(platforms)}  
**数据量**: {metrics['total_content']} 条内容

---

## 一、执行摘要

本次分析覆盖 {', '.join(platforms)} 等平台，共采集 {metrics['total_content']} 条 {industry} 行业内容。
发现爆款内容 {metrics['viral_count']} 条，平均互动量 {metrics['avg_interaction_per_content']:.0f}。

---

## 二、行业大盘数据

| 指标 | 数值 |
|------|------|
| 分析内容总数 | {metrics['total_content']} |
| 总互动量 | {metrics['total_interactions']:,} |
| 平均互动/内容 | {metrics['avg_interaction_per_content']:.0f} |
| 爆款内容数 | {metrics['viral_count']} |

---

## 三、高频关键词

{keyword_section}

---

## 四、TOP爆款内容

| 标题 | 平台 | 互动量 |
|------|------|--------|
{viral_section}

---

## 五、平台分布

| 平台 | 内容数 | 占比 |
|------|--------|------|
"""
    for platform, items in data_by_platform.items():
        pct = len(items) / metrics['total_content'] * 100 if metrics['total_content'] else 0
        report += f"| {platform} | {len(items)} | {pct:.1f}% |\n"

    report += """
---

## 六、内容策略建议

> 根据以上数据，建议内容方向：

1. **重点关注高频关键词**：围绕用户搜索热词创作内容
2. **参考爆款结构**：分析TOP爆款的标题公式和内容框架
3. **平台差异化**：根据各平台用户习惯调整内容风格

---

## 七、关键词体系（待完善）

### 主关键词
- [需结合5118数据补充]

### 商机热词  
- [需结合5118数据补充]

### 用户痛点词
- [需结合需求挖掘结果补充]
"""

    return report


def main():
    parser = argparse.ArgumentParser(description="行业分析工具")
    parser.add_argument("--industry", required=True, help="行业名称，如 护肤品")
    parser.add_argument("--brand", default="", help="品牌名称")
    parser.add_argument("--keyword", help="搜索关键词（默认使用行业名称）")
    parser.add_argument("--platforms", nargs="+",
                        default=["douyin", "xiaohongshu"],
                        choices=["douyin", "xiaohongshu", "weibo"],
                        help="分析平台")
    parser.add_argument("--limit", type=int, default=200, help="每平台数据量")
    parser.add_argument("--output", type=str, help="报告输出路径")

    args = parser.parse_args()
    keyword = args.keyword or args.industry

    print(f"🔍 开始行业分析: {args.industry}")
    print(f"关键词: {keyword}")
    print(f"平台: {', '.join(args.platforms)}")
    print("-" * 40)

    # 从各平台获取数据
    data_by_platform = {}
    for platform in args.platforms:
        print(f"正在抓取 {platform} 数据...")
        data = fetch_platform_data(keyword, platform, args.limit)
        if data:
            data_by_platform[platform] = data

    if not data_by_platform:
        print("❌ 未获取到任何数据，请检查网络或爬虫脚本")
        sys.exit(1)

    # 计算指标
    print("\n📊 分析数据中...")
    all_content = [item for items in data_by_platform.values() for item in items]
    metrics = calculate_industry_metrics(data_by_platform)
    keywords = extract_keywords_from_content(all_content)

    # 生成报告
    report = generate_report(args.industry, args.brand, data_by_platform, metrics, keywords)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n✅ 报告已保存到: {args.output}")
    else:
        print("\n" + report)


if __name__ == "__main__":
    main()
