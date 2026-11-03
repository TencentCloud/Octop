#!/usr/bin/env python3
"""
Medical Advice Skill - Demo Mode
演示技能如何整合 PubMed 和 OpenFDA 数据提供医疗建议
"""

import json
from datetime import datetime

# 模拟数据（实际使用时会从 API 获取）
MOCK_PUBMED_RESULTS = [
    {
        "pmid": "30123456",
        "title": "Management of Chronic Cough in Adults: A Systematic Review",
        "authors": "Smith J, Johnson A, Williams B",
        "journal": "Journal of Respiratory Medicine",
        "pubdate": "2024-02-15",
        "abstract": "慢性咳嗽是临床常见问题。本综述总结了成人慢性咳嗽的主要病因包括上气道咳嗽综合征、哮喘、胃食管反流病等。治疗应根据病因进行针对性处理...",
        "link": "https://pubmed.ncbi.nlm.nih.gov/30123456/"
    },
    {
        "pmid": "30234567", 
        "title": "Effectiveness of Honey vs Over-the-Counter Cough Medicines",
        "authors": "Chen L, Wang Y, Liu X",
        "journal": "Pediatrics International",
        "pubdate": "2023-11-20",
        "abstract": "本研究比较了蜂蜜与非处方止咳药对咳嗽的效果。结果显示蜂蜜在缓解夜间咳嗽方面效果相当或优于某些非处方药物，且副作用更少...",
        "link": "https://pubmed.ncbi.nlm.nih.gov/30234567/"
    }
]

MOCK_OPENFDA_RESULTS = [
    {
        "brand_name": "Advil",
        "generic_name": "Ibuprofen",
        "manufacturer": "Pfizer Consumer Healthcare",
        "purpose": "Pain reliever/Fever reducer",
        "indication": "暂时缓解：头痛、牙痛、背痛、痛经、普通感冒、肌肉疼痛、轻度关节炎疼痛、退烧",
        "warning": "⚠️ 过敏警告：可能导致严重过敏反应\n⚠️ 胃出血警告：含有 NSAID，可能引起严重胃出血\n⚠️ 心脏病和中风警告：增加心脏病发作和中风风险",
        "active_ingredient": "Ibuprofen USP, 200 mg (NSAID)",
        "route": "Oral",
        "source_url": "https://api.fda.gov/drug/label.json"
    }
]

def analyze_symptoms(symptoms, duration, context=""):
    """症状分析函数"""
    analysis = {
        "可能的原因": [],
        "严重程度": "",
        "建议科室": "",
        "家庭护理": [],
        "需要就医的情况": []
    }
    
    # 简单的症状匹配逻辑（实际应该更复杂）
    if "咳嗽" in symptoms:
        analysis["可能的原因"] = [
            "上呼吸道感染（感冒、流感）",
            "过敏（花粉、尘螨、宠物皮屑）",
            "气温变化引起的呼吸道刺激",
            "胃食管反流",
            "慢性咽炎"
        ]
        analysis["严重程度"] = "轻度至中度（如无其他严重症状）"
        analysis["建议科室"] = "呼吸内科 / 全科"
        analysis["家庭护理"] = [
            "保持室内湿度 50-60%",
            "多喝温水，避免辛辣刺激性食物",
            "保证充足睡眠",
            "出门戴口罩，避免冷空气直接刺激",
            "睡前可喝一勺蜂蜜缓解夜间咳嗽"
        ]
        analysis["需要就医的情况"] = [
            "咳嗽持续超过 2 周无缓解",
            "伴有高热（超过 38.5°C）",
            "出现呼吸困难、胸痛",
            "咳血或痰中带血",
            "夜间咳醒，影响睡眠"
        ]
    elif "头痛" in symptoms:
        analysis["可能的原因"] = [
            "紧张性头痛",
            "偏头痛",
            "睡眠不足或睡眠质量差",
            "眼睛疲劳（长时间看屏幕）",
            "脱水"
        ]
        analysis["严重程度"] = "轻度至中度"
        analysis["建议科室"] = "神经内科 / 全科"
        analysis["家庭护理"] = [
            "保证充足睡眠",
            "减少屏幕时间，每小时休息 5-10 分钟",
            "多喝水",
            "适度运动，放松身心",
            "避免咖啡因过量摄入"
        ]
        analysis["需要就医的情况"] = [
            "头痛突然发作且非常剧烈（雷击样头痛）",
            "伴有发热、颈部僵硬",
            "伴有视力改变、言语不清",
            "头部受伤后出现的头痛",
            "头痛模式发生改变或频率增加"
        ]
    else:
        analysis["可能的原因"] = ["需要更多症状信息"]
        analysis["严重程度"] = "待评估"
        analysis["建议科室"] = "全科（初步评估）"
        analysis["家庭护理"] = ["休息、观察症状变化"]
        analysis["需要就医的情况"] = ["症状持续或加重"]
    
    return analysis

def format_response(symptoms, duration, query_pubmed=False, query_openfda=False):
    """格式化响应"""
    response = []
    
    # 症状分析
    analysis = analyze_symptoms(symptoms, duration)
    
    response.append("=" * 60)
    response.append("🩺 医疗咨询建议")
    response.append("=" * 60)
    response.append("")
    
    response.append("【症状分析】")
    response.append(f"根据您的描述（{symptoms}，持续{duration}），可能的原因包括：")
    for i, cause in enumerate(analysis["可能的原因"], 1):
        response.append(f"  {i}. {cause}")
    response.append("")
    
    response.append(f"严重程度评估：{analysis['严重程度']}")
    response.append(f"建议科室：{analysis['建议科室']}")
    response.append("")
    
    # PubMed 文献参考
    if query_pubmed:
        response.append("【权威文献参考】📚")
        response.append("根据 PubMed 医学文献：")
        for i, paper in enumerate(MOCK_PUBMED_RESULTS, 1):
            response.append(f"")
            response.append(f"[{i}] {paper['title']}")
            response.append(f"    📖 {paper['journal']} | {paper['pubdate']}")
            response.append(f"    👤 {paper['authors']}")
            response.append(f"    📝 {paper['abstract'][:150]}...")
            response.append(f"    🔗 {paper['link']}")
        response.append("")
    
    # OpenFDA 药品信息
    if query_openfda:
        response.append("【药品信息参考】💊")
        response.append("根据 OpenFDA 数据库：")
        for drug in MOCK_OPENFDA_RESULTS:
            response.append(f"")
            response.append(f"📌 {drug['brand_name']} ({drug['generic_name']})")
            response.append(f"   用途：{drug['purpose']}")
            response.append(f"   有效成分：{drug['active_ingredient']}")
            response.append(f"   适应症：{drug['indication'][:100]}...")
            response.append(f"   ⚠️ 警告：{drug['warning'][:100]}...")
        response.append("")
    
    # 建议
    response.append("【建议】")
    response.append("家庭护理：")
    for tip in analysis["家庭护理"]:
        response.append(f"  • {tip}")
    response.append("")
    
    response.append("需要就医的情况：")
    for condition in analysis["需要就医的情况"]:
        response.append(f"  ⚠️ {condition}")
    response.append("")
    
    # 免责声明
    response.append("=" * 60)
    response.append("⚠️  重要提醒")
    response.append("=" * 60)
    response.append("")
    response.append("我不是医生，以上建议仅供参考，不能替代专业医疗诊断。")
    response.append("如果症状严重或持续不缓解，请及时就医。")
    response.append("")
    response.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    response.append("数据来源：PubMed (NIH), OpenFDA (FDA) - 模拟数据")
    
    return "\n".join(response)

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🏥 医疗咨询技能 - 演示模式")
    print("=" * 60)
    print("\n演示场景：用户询问'最近喉咙一直咳嗽，为什么，气温变化无常'\n")
    
    response = format_response(
        symptoms="喉咙咳嗽",
        duration="最近几天",
        query_pubmed=True,
        query_openfda=True
    )
    
    print(response)
