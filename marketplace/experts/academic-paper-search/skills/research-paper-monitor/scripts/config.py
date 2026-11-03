#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
科研文献监测配置脚本
交互式设置用户配置
"""

import json
import os
import sys

CONFIG_DIR = os.path.expanduser("~/.openclaw/research-monitor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
PAPERS_DIR = os.path.expanduser("~/.openclaw/research-papers")

DEFAULT_CONFIG = {
    "user_profile": {
        "name": "",
        "institution": "",
        "research_field": ""
    },
    "keywords": [],
    "sources": ["arxiv", "pubmed", "google_scholar"],
    "filters": {
        "max_papers_per_source": 20,
        "min_score_threshold": 50,
        "date_range_days": 1
    },
    "notification": {
        "enabled": False,
        "feishu_webhook": "",
        "min_score_for_notification": 80
    },
    "storage": {
        "papers_dir": PAPERS_DIR,
        "index_file": os.path.join(CONFIG_DIR, "literature-index.json")
    }
}

AVAILABLE_SOURCES = [
    ("arxiv", "arXiv (物理、数学、计算机、生物预印本)"),
    ("pubmed", "PubMed (生物医学、生命科学)"),
    ("google_scholar", "Google Scholar (全学科)"),
    ("cnki", "CNKI知网 (中文学术)"),
    ("ieee", "IEEE Xplore (工程技术)"),
    ("semantic_scholar", "Semantic Scholar (AI增强搜索)")
]


def ensure_directories():
    """确保必要的目录存在"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(PAPERS_DIR, exist_ok=True)


def input_with_default(prompt, default=""):
    """带默认值的输入"""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    return input(f"{prompt}: ").strip()


def configure_user_profile():
    """配置用户信息"""
    print("\n=== 用户基本信息 ===")
    name = input_with_default("您的姓名")
    institution = input_with_default("所属机构（大学/研究所/公司）")
    field = input_with_default("主要研究领域（如：人工智能、生物医学、材料科学）")
    
    return {
        "name": name,
        "institution": institution,
        "research_field": field
    }


def configure_keywords():
    """配置关注关键词"""
    print("\n=== 关注关键词设置 ===")
    print("请输入您关注的研究关键词，用于筛选相关论文")
    print("示例：large language model, computer vision, drug discovery")
    print("最多10个关键词，直接回车结束")
    
    keywords = []
    for i in range(10):
        keyword = input(f"关键词 {i+1}: ").strip()
        if not keyword:
            break
        keywords.append(keyword.lower())
    
    if not keywords:
        print("警告：未设置关键词，将采集所有论文")
    
    return keywords


def configure_sources():
    """配置监测信源"""
    print("\n=== 学术信源选择 ===")
    print("可选信源：")
    for i, (key, desc) in enumerate(AVAILABLE_SOURCES, 1):
        print(f"  {i}. {desc}")
    
    print("\n请输入要启用的信源编号（多个用逗号分隔，如：1,2,3）")
    print("直接回车使用默认：arXiv + PubMed + Google Scholar")
    
    selection = input("选择: ").strip()
    
    if not selection:
        return ["arxiv", "pubmed", "google_scholar"]
    
    selected_sources = []
    try:
        indices = [int(x.strip()) for x in selection.split(",")]
        for idx in indices:
            if 1 <= idx <= len(AVAILABLE_SOURCES):
                selected_sources.append(AVAILABLE_SOURCES[idx-1][0])
    except ValueError:
        print("输入格式错误，使用默认设置")
        return ["arxiv", "pubmed", "google_scholar"]
    
    return selected_sources if selected_sources else ["arxiv"]


def configure_notification():
    """配置推送通知"""
    print("\n=== 推送通知设置 ===")
    print("是否启用飞书推送？（每天将高相关论文推送到飞书）")
    
    enable = input("启用推送? (y/n) [n]: ").strip().lower()
    
    if enable == 'y':
        webhook = input("请输入飞书机器人 Webhook URL: ").strip()
        if webhook:
            return {
                "enabled": True,
                "feishu_webhook": webhook,
                "min_score_for_notification": 80
            }
    
    return {
        "enabled": False,
        "feishu_webhook": "",
        "min_score_for_notification": 80
    }


def save_config(config):
    """保存配置到文件"""
    ensure_directories()
    
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 配置已保存到: {CONFIG_FILE}")


def display_config(config):
    """显示当前配置"""
    print("\n=== 当前配置预览 ===")
    print(f"用户: {config['user_profile']['name']} ({config['user_profile']['institution']})")
    print(f"研究领域: {config['user_profile']['research_field']}")
    print(f"关键词: {', '.join(config['keywords']) if config['keywords'] else '(未设置)'}")
    print(f"信源: {', '.join(config['sources'])}")
    print(f"推送: {'已启用' if config['notification']['enabled'] else '未启用'}")


def main():
    """主函数"""
    print("=" * 50)
    print("科研文献智能监测 - 配置向导")
    print("=" * 50)
    
    # 检查是否已有配置
    existing_config = None
    if os.path.exists(CONFIG_FILE):
        print(f"\n发现已有配置文件")
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            existing_config = json.load(f)
        
        update = input("是否更新配置? (y/n) [y]: ").strip().lower()
        if update == 'n':
            print("保持现有配置")
            display_config(existing_config)
            return
    
    # 开始配置
    config = DEFAULT_CONFIG.copy()
    if existing_config:
        config.update(existing_config)
    
    # 用户配置
    config['user_profile'] = configure_user_profile()
    
    # 关键词配置
    config['keywords'] = configure_keywords()
    
    # 信源配置
    config['sources'] = configure_sources()
    
    # 推送配置
    config['notification'] = configure_notification()
    
    # 保存配置
    save_config(config)
    
    # 初始化索引文件
    index_file = config['storage']['index_file']
    if not os.path.exists(index_file):
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump({"papers": []}, f, ensure_ascii=False, indent=2)
        print(f"✓ 文献索引已初始化: {index_file}")
    
    # 显示配置
    display_config(config)
    
    print("\n" + "=" * 50)
    print("配置完成！")
    print("=" * 50)
    print("\n下一步:")
    print("1. 测试运行: python monitor.py")
    print("2. 设置定时任务: 编辑 HEARTBEAT.md")
    print("\n祝科研顺利！")


if __name__ == "__main__":
    main()
