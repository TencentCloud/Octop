"""
违禁词检测工具
用法：python detect_forbidden_words.py --text "文章内容" --platform douyin
"""

import argparse
import json
import re
import sys

# 各平台违禁词库
FORBIDDEN_WORDS = {
    "common": {
        "最高级": ["最好", "第一", "顶级", "绝对", "100%", "最强", "最优", "业界最", "行业第一", "全国第一", "国内最"],
        "承诺性": ["保证", "承诺", "必须", "肯定", "一定有效", "百分百", "完全"],
        "虚假宣传": ["真实案例", "纯天然无添加", "零添加", "纯植物", "无副作用"],
    },
    "medical": {
        "医疗功效": ["治疗", "治愈", "消炎", "杀菌", "抗菌", "消毒", "药效", "医治", "康复", "痊愈"],
        "疾病名称": ["糖尿病", "高血压", "癌症", "肿瘤", "抑郁症", "焦虑症"],
        "夸大效果": ["立竿见影", "迅速见效", "快速康复", "药到病除"],
    },
    "douyin": {
        "平台引流": ["微信", "微信号", "wx", "wechat", "二维码", "私聊", "私下联系", "加我", "扫码"],
        "竞争排斥": ["比抖音好", "抖音不如"],
        "不当引导": ["关注后私信", "粉丝福利群"],
    },
    "xiaohongshu": {
        "平台引流": ["微信", "wx", "wechat", "私下联系", "抖音账号"],
        "广告词": ["广告", "推广", "付费合作"],
        "不当比较": ["比小红书好"],
    },
    "wechat": {
        "引流词": ["关注公众号", "扫二维码关注"],
        "诱导传播": ["转发给N个人", "必须转发", "不转不是中国人"],
    }
}

# 替换建议
REPLACEMENT_SUGGESTIONS = {
    "最好": "非常好 / 深受好评",
    "第一": "领先 / 优质",
    "保证": "通常 / 一般",
    "治疗": "改善 / 调节",
    "消炎": "舒缓 / 呵护",
    "微信": "主页 / 简介",
    "二维码": "主页链接",
    "私聊": "私信",
    "100%": "大多数",
    "立竿见影": "持续使用后",
    "无副作用": "温和配方",
    "纯天然": "精选成分",
}


def detect_forbidden_words(text: str, platform: str = "common") -> dict:
    """
    检测文本中的违禁词

    Returns:
        dict: {
            "has_forbidden": bool,
            "violations": [{"word": str, "category": str, "suggestion": str, "positions": [int]}],
            "risk_level": "high" | "medium" | "low",
            "cleaned_text": str (with violations marked)
        }
    """
    violations = []
    marked_text = text

    # 合并通用词库和平台特定词库
    check_categories = dict(FORBIDDEN_WORDS["common"])
    check_categories.update(FORBIDDEN_WORDS.get("medical", {}))
    if platform in FORBIDDEN_WORDS:
        check_categories.update(FORBIDDEN_WORDS[platform])

    for category, words in check_categories.items():
        for word in words:
            positions = [m.start() for m in re.finditer(re.escape(word), text, re.IGNORECASE)]
            if positions:
                suggestion = REPLACEMENT_SUGGESTIONS.get(word, "请使用温和表达方式替代")
                violations.append({
                    "word": word,
                    "category": category,
                    "suggestion": suggestion,
                    "positions": positions,
                    "count": len(positions)
                })
                # 标记违规词
                marked_text = marked_text.replace(word, f"【⚠️{word}⚠️】")

    # 判断风险等级
    high_risk_categories = {"医疗功效", "疾病名称", "平台引流", "最高级"}
    risk_level = "low"
    if violations:
        for v in violations:
            if v["category"] in high_risk_categories:
                risk_level = "high"
                break
        if risk_level != "high":
            risk_level = "medium"

    return {
        "has_forbidden": len(violations) > 0,
        "violations_count": len(violations),
        "risk_level": risk_level,
        "violations": violations,
        "marked_text": marked_text
    }


def format_report(result: dict, platform: str) -> str:
    """格式化检测报告"""
    lines = [
        f"=== 违禁词检测报告 ===",
        f"平台: {platform}",
        f"风险等级: {'🔴 高风险' if result['risk_level'] == 'high' else '🟡 中风险' if result['risk_level'] == 'medium' else '🟢 低风险'}",
        f"发现违规词: {result['violations_count']} 个",
        ""
    ]

    if result["violations"]:
        lines.append("违规详情：")
        for i, v in enumerate(result["violations"], 1):
            lines.append(f"\n{i}. 【{v['word']}】")
            lines.append(f"   类别: {v['category']}")
            lines.append(f"   出现次数: {v['count']}")
            lines.append(f"   建议替换: {v['suggestion']}")
        lines.append("")
        lines.append("标注后的文本：")
        lines.append(result["marked_text"])
    else:
        lines.append("✅ 未发现违禁词，内容合规！")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="新媒体违禁词检测工具")
    parser.add_argument("--text", type=str, help="待检测文本")
    parser.add_argument("--file", type=str, help="待检测文本文件路径")
    parser.add_argument("--platform", type=str, default="common",
                        choices=["common", "douyin", "xiaohongshu", "wechat"],
                        help="目标平台")
    parser.add_argument("--output", type=str, help="输出结果到JSON文件")
    parser.add_argument("--json", action="store_true", help="以JSON格式输出")

    args = parser.parse_args()

    # 获取文本内容
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        print("错误：请通过 --text 或 --file 提供待检测文本")
        sys.exit(1)

    result = detect_forbidden_words(text, args.platform)

    if args.json:
        output = json.dumps(result, ensure_ascii=False, indent=2)
        print(output)
    else:
        print(format_report(result, args.platform))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output}")

    # 高风险时返回非零退出码
    sys.exit(1 if result["risk_level"] == "high" else 0)


if __name__ == "__main__":
    main()
