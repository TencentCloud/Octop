#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中华护理学会团体标准列表爬取脚本
功能：
  1. 爬取 hltb.kxj.org.cn 全部标准列表
  2. 根据诊断关键词匹配最相关标准
  3. 下载匹配标准的PDF文件
用法：
  python fetch_standards.py --diagnosis "气管切开" --output_dir "/tmp/nursing_std"
"""

import requests
import re
import os
import json
import argparse
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE_URL = "https://hltb.kxj.org.cn"
STANDARD_LIST_URL = f"{BASE_URL}/index/tuanti/index.html"
STANDARD_DETAIL_TPL = f"{BASE_URL}/index/tuanti/standard.html?team_standard_id={{sid}}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": BASE_URL,
}

# 诊断关键词 → 标准匹配规则
DIAGNOSIS_KEYWORD_MAP = {
    "气管切开": ["气管切开", "气道护理"],
    "气管": ["气管切开", "气道护理", "机械通气"],
    "机械通气": ["机械通气", "气管", "气道"],
    "呼吸": ["氧气吸入", "气道", "机械通气"],
    "氧气": ["氧气吸入"],
    "肿瘤": ["癌性疼痛", "化疗"],
    "癌": ["癌性疼痛", "化疗"],
    "化疗": ["化疗", "癌性疼痛"],
    "疼痛": ["癌性疼痛", "疼痛"],
    "造口": ["肠造口"],
    "肠造口": ["肠造口"],
    "便秘": ["便秘", "耳穴"],
    "认知": ["认知障碍", "激越"],
    "痴呆": ["认知障碍", "激越"],
    "约束": ["身体约束"],
    "消毒": ["医疗器械清洗"],
    "器械": ["医疗器械清洗"],
}


def fetch_all_standards():
    """爬取全部标准列表，返回 [{id, code, name, domain, url}] """
    try:
        resp = requests.get(STANDARD_LIST_URL, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        
        standards = []
        # 查找表格行
        rows = soup.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                links = row.find_all("a", href=True)
                if links:
                    href = links[0].get("href", "")
                    # 提取 team_standard_id
                    sid_match = re.search(r"team_standard_id=(\d+)", href)
                    if sid_match:
                        sid = int(sid_match.group(1))
                        # 表格结构：序号 | 标准编号（带链接） | 标准名称（带链接） | 专业领域 | 状态 | 发布日期 | 实施日期
                        # 通过链接文本获取标准编号和名称
                        all_links = row.find_all("a", href=True)
                        # 标准编号：第一个链接（T/CNAS XX格式）
                        code = all_links[0].get_text(strip=True) if len(all_links) > 0 else ""
                        # 标准名称：第二个链接（中文名称）
                        name = all_links[1].get_text(strip=True) if len(all_links) > 1 else code
                        if not name or name == code:
                            # 尝试从所有td中找中文名称
                            for col in cols:
                                text = col.get_text(strip=True)
                                if any('\u4e00' <= c <= '\u9fff' for c in text) and len(text) > 4:
                                    name = text
                                    break
                        # 专业领域：找包含科/医的列
                        domain = ""
                        for col in cols:
                            text = col.get_text(strip=True)
                            if ("科" in text or "医" in text) and len(text) < 20:
                                domain = text
                                break
                        
                        standards.append({
                            "id": sid,
                            "code": code,
                            "name": name,
                            "domain": domain,
                            "url": STANDARD_DETAIL_TPL.format(sid=sid)
                        })
        
        if not standards:
            # 尝试备用解析方式
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                sid_match = re.search(r"team_standard_id=(\d+)", href)
                if sid_match:
                    sid = int(sid_match.group(1))
                    name = link.get_text(strip=True)
                    if name and sid not in [s["id"] for s in standards]:
                        standards.append({
                            "id": sid,
                            "code": f"T/CNAS {sid:02d}",
                            "name": name,
                            "domain": "",
                            "url": STANDARD_DETAIL_TPL.format(sid=sid)
                        })
        
        return standards
    except Exception as e:
        print(f"[WARN] 获取标准列表失败: {e}")
        # 返回已知的前10项作为降级数据
        return get_fallback_standards()


def get_fallback_standards():
    """降级数据：已知的中华护理学会团体标准"""
    return [
        {"id": 1, "code": "T/CNAS 01-2019", "name": "成人癌性疼痛护理", "domain": "肿瘤外科",
         "url": STANDARD_DETAIL_TPL.format(sid=1)},
        {"id": 2, "code": "T/CNAS 02-2019", "name": "便秘的耳穴贴压技术", "domain": "外科",
         "url": STANDARD_DETAIL_TPL.format(sid=2)},
        {"id": 3, "code": "T/CNAS 03-2019", "name": "气管切开非机械通气患者气道护理", "domain": "呼吸科",
         "url": STANDARD_DETAIL_TPL.format(sid=3)},
        {"id": 4, "code": "T/CNAS 04-2019", "name": "住院患者身体约束护理", "domain": "外科",
         "url": STANDARD_DETAIL_TPL.format(sid=4)},
        {"id": 5, "code": "T/CNAS 05-2019", "name": "化疗药物外渗预防及处理", "domain": "外科",
         "url": STANDARD_DETAIL_TPL.format(sid=5)},
        {"id": 6, "code": "T/CNAS 06-2019", "name": "认知障碍患者激越行为非药物管理", "domain": "外科",
         "url": STANDARD_DETAIL_TPL.format(sid=6)},
        {"id": 7, "code": "T/CNAS 07-2019", "name": "成人肠造口护理", "domain": "内科",
         "url": STANDARD_DETAIL_TPL.format(sid=7)},
        {"id": 8, "code": "T/CNAS 08-2019", "name": "成人氧气吸入疗法护理", "domain": "呼吸科",
         "url": STANDARD_DETAIL_TPL.format(sid=8)},
        {"id": 9, "code": "T/CNAS 09-2019", "name": "医疗器械清洗技术操作", "domain": "外科",
         "url": STANDARD_DETAIL_TPL.format(sid=9)},
        {"id": 10, "code": "T-CNAS 10-2020", "name": "成人有创机械通气气道内吸引技术操作", "domain": "呼吸科",
         "url": STANDARD_DETAIL_TPL.format(sid=10)},
    ]


def match_standards(diagnosis, symptoms, all_standards):
    """根据诊断和症状匹配最相关标准，返回前3个"""
    diagnosis_lower = diagnosis.lower()
    symptoms_lower = (symptoms or "").lower()
    combined_text = diagnosis_lower + " " + symptoms_lower
    
    scored = []
    for std in all_standards:
        score = 0
        std_name = std["name"]
        
        # 直接名称匹配
        for keyword, targets in DIAGNOSIS_KEYWORD_MAP.items():
            if keyword in combined_text:
                for target in targets:
                    if target in std_name:
                        score += 10
        
        # 通用相关度计算（字符级别）
        for char in combined_text:
            if char in std_name:
                score += 0.5
        
        # 专科领域匹配
        domain_keywords = {
            "呼吸": ["呼吸", "气道", "肺", "氧气"],
            "肿瘤": ["肿瘤", "癌", "化疗"],
            "消化": ["消化", "胃", "肠"],
            "心血管": ["心", "血管", "心脏"],
            "神经": ["神经", "脑", "认知"],
        }
        for domain, kws in domain_keywords.items():
            for kw in kws:
                if kw in combined_text and domain in std.get("domain", ""):
                    score += 3
        
        scored.append((score, std))
    
    # 按分数排序，取前3
    scored.sort(key=lambda x: x[0], reverse=True)
    top3 = [s[1] for s in scored[:3] if s[0] > 0]
    
    # 如果没有匹配，默认用成人氧气吸入（最通用）
    if not top3:
        top3 = [s for s in all_standards if s["id"] == 8][:1]
    
    return top3


def search_standards_by_operation_name(operation_name, all_standards):
    """根据护理操作名称搜索相关标准（支持模糊匹配）
    
    Args:
        operation_name: 护理操作名称，如"气管切开气道护理"
        all_standards: 所有标准列表
    
    Returns:
        匹配的标准列表（按相关度排序）
    """
    if not operation_name:
        return []
    
    operation_lower = operation_name.lower()
    scored = []
    
    for std in all_standards:
        score = 0
        std_name = std["name"]
        std_code = std.get("code", "")
        
        # 精确匹配操作名称
        if operation_lower in std_name.lower():
            score += 20
        
        # 分词匹配（中文按字符）
        op_words = set(operation_lower.replace(" ", ""))
        std_words = set(std_name.replace(" ", ""))
        common_words = op_words & std_words
        score += len(common_words) * 3
        
        # 关键词匹配
        keywords = operation_lower.split()
        for keyword in keywords:
            if len(keyword) >= 2 and keyword in std_name:
                score += 10
        
        # 领域匹配
        operation_domain_map = {
            "气道": "呼吸", "气管": "呼吸", "氧气": "呼吸", "呼吸": "呼吸",
            "造口": "消化", "肠": "消化", "胃": "消化",
            "疼痛": "肿瘤", "化疗": "肿瘤", "癌": "肿瘤",
            "认知": "神经", "痴呆": "神经",
            "约束": "综合", "消毒": "综合",
        }
        
        for op_key, domain in operation_domain_map.items():
            if op_key in operation_lower and domain in std.get("domain", ""):
                score += 5
        
        if score > 0:
            scored.append((score, std))
    
    # 按分数排序
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:5]]  # 返回前5个最相关的标准


def fetch_pdf_url(standard_url):
    """从标准详情页提取PDF下载链接"""
    try:
        resp = requests.get(standard_url, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 查找PDF下载链接
        pdf_urls = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if ".pdf" in href.lower() or "download" in href.lower() or "下载" in text:
                full_url = urljoin(BASE_URL, href)
                pdf_urls.append(full_url)
        
        # 也查找包含"标准下载"区域的链接
        for section in soup.find_all(["div", "section", "li"]):
            section_text = section.get_text()
            if "标准下载" in section_text or "下载" in section_text:
                for a in section.find_all("a", href=True):
                    href = a.get("href", "")
                    if href:
                        full_url = urljoin(BASE_URL, href)
                        if full_url not in pdf_urls:
                            pdf_urls.append(full_url)
        
        # 返回也包含页面文本内容作为备用
        page_text = soup.get_text(separator="\n")
        return pdf_urls, page_text
    
    except Exception as e:
        print(f"[WARN] 获取详情页失败: {e}")
        return [], ""


def download_pdf(pdf_url, output_path):
    """下载PDF文件"""
    try:
        resp = requests.get(pdf_url, headers=HEADERS, timeout=60, stream=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            print(f"[OK] PDF已下载: {output_path} ({len(resp.content)//1024}KB)")
            return True
        else:
            print(f"[WARN] PDF下载失败，状态码: {resp.status_code}")
            return False
    except Exception as e:
        print(f"[WARN] PDF下载异常: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="中华护理学会标准爬取与PDF下载")
    parser.add_argument("--diagnosis", default="", help="患者诊断")
    parser.add_argument("--symptoms", default="", help="症状描述")
    parser.add_argument("--operation_name", default="", help="护理操作名称（用于精确搜索相关标准）")
    parser.add_argument("--output_dir", default="/tmp/nursing_std", help="PDF输出目录")
    parser.add_argument("--list_only", action="store_true", help="只列出匹配标准，不下载PDF")
    parser.add_argument("--search_all", action="store_true", help="搜索全部标准（不筛选）")
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    print(f"[INFO] 正在获取中华护理学会团体标准列表...")
    all_standards = fetch_all_standards()
    print(f"[INFO] 共获取 {len(all_standards)} 项标准")
    
    # 确定匹配的标准
    if args.search_all:
        matched = all_standards[:10]  # 返回前10个
        print(f"[INFO] 返回前 {len(matched)} 项标准")
    elif args.operation_name:
        # 按护理操作名称搜索
        print(f"[INFO] 根据护理操作名称「{args.operation_name}」搜索相关标准...")
        matched = search_standards_by_operation_name(args.operation_name, all_standards)
        print(f"[INFO] 匹配到 {len(matched)} 项相关标准：")
    elif args.diagnosis:
        # 按诊断匹配
        print(f"[INFO] 根据诊断「{args.diagnosis}」匹配最相关标准...")
        matched = match_standards(args.diagnosis, args.symptoms, all_standards)
        print(f"[INFO] 匹配到 {len(matched)} 项相关标准：")
    else:
        print("[ERROR] 请提供 --diagnosis 或 --operation_name 参数")
        return
    
    for s in matched:
        print(f"  - [{s['code']}] {s['name']} ({s.get('domain', '')})")
    
    if args.list_only:
        result = {"matched_standards": matched, "all_count": len(all_standards)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    # 下载PDF
    results = []
    for std in matched:
        print(f"\n[INFO] 处理标准: {std['name']}")
        pdf_urls, page_text = fetch_pdf_url(std["url"])
        
        pdf_downloaded = False
        pdf_path = ""
        
        for pdf_url in pdf_urls:
            pdf_path = os.path.join(args.output_dir, f"std_{std['id']}.pdf")
            if download_pdf(pdf_url, pdf_path):
                pdf_downloaded = True
                break
            time.sleep(1)
        
        results.append({
            "standard": std,
            "pdf_downloaded": pdf_downloaded,
            "pdf_path": pdf_path if pdf_downloaded else None,
            "page_text": page_text if not pdf_downloaded else "",  # 降级用网页文本
        })
        time.sleep(0.5)
    
    # 保存结果JSON
    result_json_path = os.path.join(args.output_dir, "fetch_result.json")
    with open(result_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n[DONE] 结果已保存: {result_json_path}")
    return result_json_path


if __name__ == "__main__":
    main()
