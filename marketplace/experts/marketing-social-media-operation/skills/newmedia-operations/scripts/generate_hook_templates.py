"""
互动钩子话术生成工具
用法：python generate_hook_templates.py --industry "护肤品" --brand "XX品牌" --hook_type all
"""

import argparse
import json
from datetime import datetime


# 钩子模板库
HOOK_TEMPLATES = {
    "video_question": [
        "你是不是也遇到过{pain_point}？",
        "遇到{pain_point}的举个手",
        "{option_a} 还是 {option_b}？评论区告诉我",
        "你是不是还在用{wrong_method}？难怪{bad_result}！",
    ],
    "video_save": [
        "点赞收藏，不然刷着刷着就没了",
        "这条内容很重要，先收藏再看，以后肯定用得上",
        "干货有点多，建议先收藏慢慢看",
        "收藏这条，{scenario}用得上",
    ],
    "video_dm": [
        "想要{resource}的，找我发你",
        "完整版{resource}太长放不下，需要的在评论区说「{keyword}」",
        "更详细的{industry}干货整理好了，看我主页简介",
    ],
    "video_follow": [
        "这只是第一步，关注我，下期讲{next_content}",
        "想知道{topic_a}还是{topic_b}？关注后评论区告诉我",
        "关注我，每天更{content_type}干货",
    ],
    "comment_choice": [
        "给大家个选择：{option_a} 还是 {option_b}？点赞选A，评论1选B",
        "你更倾向{option_a}还是{option_b}？评论区聊聊",
    ],
    "comment_resource": [
        "有用就收藏一下～需要完整版{resource}的，我发你参考。",
        "大家的疑问我都看到啦，统一整理后会发给有需要的朋友。",
        "需要完整{resource}的朋友，评论区扣「1」",
    ],
    "comment_demand": [
        "想知道{topic_a}还是{topic_b}？评论区告诉我，优先更你们想看的！",
        "下期想看{topic_a}还是{topic_b}？投票决定",
        "你们最想了解{industry}的哪个问题？评论区告诉我",
    ],
    "comment_empathy": [
        "说说你用过最坑的{product_type}，一起吐槽",
        "在{industry}踩过哪些坑？聊聊你的经历",
        "你{industry}里有什么让你特别崩溃的事？来聊聊",
    ],
    "private_guide": [
        "想要完整{resource}的朋友，可以看我主页简介，我发你完整版。",
        "更多干货和细节我都整理好了，需要的朋友可以到主页找我领取哦。",
        "想了解具体{query}的，我单独发你详细说明，看我简介即可。",
        "每天只回复少量咨询，有需要的朋友可以通过主页联系我。",
    ],
    "welcome_message": [
        "你好～感谢关注！我会发你【{industry}干货 + 产品资料 + 常见问题解答】，方便你快速了解。",
        "你好呀～为了更好帮你，你可以简单说下你的需求，我给你针对性方案。",
        "感谢信任！后续新品、活动、干货我都会第一时间发你，不打扰、不刷屏。",
    ],
    "reactivation": [
        "好久没见你了！最近{industry}有个重要更新，发你参考看看",
        "这周出了一个{hot_topic}，刚好和{industry}相关，来看看？",
        "整理了一份{resource}，记得上次你关注过{related_topic}，发你一起看看",
    ],
}


def fill_template(template: str, variables: dict) -> str:
    """用变量填充模板"""
    try:
        return template.format(**variables)
    except KeyError:
        return template


def generate_hooks(industry: str, brand: str, hook_types: list,
                   variables: dict) -> dict:
    """生成指定类型的互动钩子"""
    result = {}

    for hook_type in hook_types:
        if hook_type == "all":
            selected_types = list(HOOK_TEMPLATES.keys())
        else:
            selected_types = [hook_type]

        for htype in selected_types:
            templates = HOOK_TEMPLATES.get(htype, [])
            generated = [fill_template(t, variables) for t in templates]
            result[htype] = generated

    return result


def format_hook_library(industry: str, brand: str, hooks: dict) -> str:
    """格式化输出话术库"""
    lines = [
        f"# {brand or industry} 互动话术库",
        f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"行业: {industry}",
        "---\n",
    ]

    type_names = {
        "video_question": "视频内 - 提问钩子",
        "video_save": "视频内 - 收藏引导",
        "video_dm": "视频内 - 私信引导",
        "video_follow": "视频内 - 关注引导",
        "comment_choice": "评论区 - 选择题型",
        "comment_resource": "评论区 - 资源分发",
        "comment_demand": "评论区 - 需求收集",
        "comment_empathy": "评论区 - 情感共鸣",
        "private_guide": "私信 - 私域引导话术",
        "welcome_message": "私信 - 自动欢迎语",
        "reactivation": "私信 - 用户唤醒",
    }

    for hook_type, templates in hooks.items():
        section_name = type_names.get(hook_type, hook_type)
        lines.append(f"## {section_name}\n")
        for i, template in enumerate(templates, 1):
            lines.append(f"{i}. {template}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="互动钩子话术生成工具")
    parser.add_argument("--industry", required=True, help="行业名称")
    parser.add_argument("--brand", default="", help="品牌名称")
    parser.add_argument("--hook_type", default="all",
                        choices=["all", "video_question", "video_save", "video_dm",
                                 "video_follow", "comment_choice", "comment_resource",
                                 "comment_demand", "comment_empathy", "private_guide",
                                 "welcome_message", "reactivation"],
                        help="钩子类型")
    parser.add_argument("--pain_point", default="[行业痛点]", help="用户痛点")
    parser.add_argument("--product_type", default="[产品类型]", help="产品类型")
    parser.add_argument("--resource", default="完整资料", help="资源名称（如：完整方案/报价单）")
    parser.add_argument("--option_a", default="[选项A]", help="选项A")
    parser.add_argument("--option_b", default="[选项B]", help="选项B")
    parser.add_argument("--output", type=str, help="输出到文件")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()

    variables = {
        "industry": args.industry,
        "brand": args.brand or args.industry,
        "pain_point": args.pain_point,
        "product_type": args.product_type,
        "resource": args.resource,
        "option_a": args.option_a,
        "option_b": args.option_b,
        "scenario": f"{args.industry}相关场景",
        "keyword": "资料",
        "next_content": f"{args.industry}进阶技巧",
        "topic_a": f"{args.industry}技巧",
        "topic_b": f"{args.industry}避坑",
        "content_type": args.industry,
        "wrong_method": f"错误的{args.industry}方法",
        "bad_result": "效果一直不好",
        "query": f"{args.industry}详情",
        "hot_topic": "行业热点",
        "related_topic": args.industry,
    }

    hooks = generate_hooks(args.industry, args.brand, [args.hook_type], variables)

    if args.json:
        output = json.dumps(hooks, ensure_ascii=False, indent=2)
        print(output)
    else:
        print(format_hook_library(args.industry, args.brand, hooks))

    if args.output:
        content = format_hook_library(args.industry, args.brand, hooks)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n话术库已保存到: {args.output}")


if __name__ == "__main__":
    main()
