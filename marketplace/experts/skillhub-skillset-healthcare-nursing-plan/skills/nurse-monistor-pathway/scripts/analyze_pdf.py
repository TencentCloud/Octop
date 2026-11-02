#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
护理操作PDF结构化分析脚本
功能：
  1. 使用 pdfplumber 提取PDF全文
  2. 利用正则+LLM对文本进行结构化提取
  3. 输出标准化JSON（含护理评估、适应症、禁忌证、准备、操作要点、并发症、干预措施）
用法：
  python analyze_pdf.py --pdf_path "xxx.pdf" --diagnosis "气管切开"
  python analyze_pdf.py --text_input "xxx" --standard_name "气管切开非机械通气患者气道护理"
"""

import argparse
import json
import os
import re
import sys


def extract_pdf_text(pdf_path):
    """提取PDF全文，使用pdfplumber"""
    try:
        import pdfplumber
        text_pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(f"=== 第{i+1}页 ===\n{page_text}")
        full_text = "\n".join(text_pages)
        print(f"[INFO] PDF提取完成，共 {len(text_pages)} 页，{len(full_text)} 字符")
        return full_text
    except ImportError:
        print("[WARN] pdfplumber未安装，尝试安装...")
        os.system(
            '"C:\\Users\\Administrator\\.workbuddy\\binaries\\python\\envs\\default\\Scripts\\pip.exe" '
            'install pdfplumber -q'
        )
        import pdfplumber
        text_pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(f"=== 第{i+1}页 ===\n{page_text}")
        return "\n".join(text_pages)
    except Exception as e:
        print(f"[ERROR] PDF提取失败: {e}")
        return ""


def rule_based_extract(text, standard_name=""):
    """基于规则的结构化提取（无需LLM的降级方案）"""
    
    def extract_section(text, patterns, max_chars=2000):
        """提取指定章节内容"""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                start = match.start()
                # 找到下一个章节
                next_section = re.search(
                    r'\n\d+[\s\.、]+[^\n]{2,20}\n', 
                    text[start+len(match.group()):start+max_chars]
                )
                end = start + (next_section.start() if next_section else max_chars)
                return text[start:end].strip()
        return ""
    
    result = {
        "standard_name": standard_name,
        "nursing_assessment": "",
        "indications": [],
        "contraindications": [],
        "preparations": {
            "drugs": "",
            "equipment": "",
            "patient_prep": "",
            "environment_prep": ""
        },
        "operation_key_points": "",
        "complications": [],
        "intervention_measures": "",
        "precautions": ""
    }
    
    # 护理评估
    assessment_text = extract_section(text, [
        r'护理评估[^\n]*\n', r'评估[^\n]*\n', r'4[\s\.]+护理评估',
        r'一[、．].*评估', r'assessment'
    ])
    result["nursing_assessment"] = assessment_text[:800] if assessment_text else "参见标准文件第三章护理评估部分"
    
    # 适应症
    indications_text = extract_section(text, [
        r'适应[症证][^\n]*\n', r'适用范围[^\n]*\n', r'indication',
        r'2[\s\.]+适应', r'3[\s\.]+适应'
    ])
    if indications_text:
        items = re.findall(r'[a-zA-Z\d\u4e00-\u9fff][）\)、]([^\n]{5,100})', indications_text)
        result["indications"] = items[:10] if items else [indications_text[:200]]
    
    # 禁忌证
    contra_text = extract_section(text, [
        r'禁忌[症证][^\n]*\n', r'contraindication', r'禁忌[^\n]*\n'
    ])
    if contra_text:
        items = re.findall(r'[a-zA-Z\d\u4e00-\u9fff][）\)、]([^\n]{5,100})', contra_text)
        result["contraindications"] = items[:10] if items else [contra_text[:200]]
    
    # 准备（药物、器械）
    prep_text = extract_section(text, [
        r'用物准备[^\n]*\n', r'操作准备[^\n]*\n', r'准备[^\n]*\n',
        r'物品准备[^\n]*\n', r'器械准备[^\n]*\n'
    ])
    if prep_text:
        # 药物
        drug_match = re.search(r'药物[^\n]{0,200}', prep_text)
        result["preparations"]["drugs"] = drug_match.group(0) if drug_match else ""
        # 器械
        equip_match = re.search(r'(器械|仪器|设备|物品)[^\n]{0,300}', prep_text)
        result["preparations"]["equipment"] = equip_match.group(0)[:300] if equip_match else prep_text[:300]
        # 患者准备
        patient_match = re.search(r'患者准备[^\n]{0,200}', prep_text)
        result["preparations"]["patient_prep"] = patient_match.group(0) if patient_match else ""
    
    # 操作要点
    op_text = extract_section(text, [
        r'操作要点[^\n]*\n', r'操作步骤[^\n]*\n', r'护理操作[^\n]*\n',
        r'实施[^\n]*\n', r'操作程序[^\n]*\n'
    ], max_chars=3000)
    result["operation_key_points"] = op_text[:1500] if op_text else "参见标准文件操作步骤章节"
    
    # 并发症
    comp_text = extract_section(text, [
        r'并发症[^\n]*\n', r'complication', r'不良反应[^\n]*\n'
    ])
    if comp_text:
        items = re.findall(r'[a-zA-Z\d\u4e00-\u9fff][）\)、]([^\n]{3,60})', comp_text)
        result["complications"] = items[:10] if items else [comp_text[:200]]
    
    # 干预与处理措施
    intervention_text = extract_section(text, [
        r'干预[^\n]*\n', r'处理[^\n]*\n', r'应急处理[^\n]*\n',
        r'并发症.*处理', r'注意事项[^\n]*\n'
    ], max_chars=2000)
    result["intervention_measures"] = intervention_text[:1000] if intervention_text else ""
    
    # 注意事项
    precaution_text = extract_section(text, [
        r'注意事项[^\n]*\n', r'注意[^\n]*\n', r'precaution'
    ])
    result["precautions"] = precaution_text[:500] if precaution_text else ""
    
    return result


def llm_structured_extract(text, standard_name, diagnosis=""):
    """使用LLM进行结构化提取"""
    # 尝试使用 openai / anthropic / 本地API
    # 优先检查环境变量中的API配置
    
    api_key = (os.environ.get("OPENAI_API_KEY") or 
               os.environ.get("ANTHROPIC_API_KEY") or
               os.environ.get("DEEPSEEK_API_KEY"))
    
    if not api_key:
        print("[WARN] 未找到LLM API密钥，降级使用规则提取")
        return None
    
    prompt = f"""你是专业的护理标准文档分析专家。请从以下护理操作标准文档中提取结构化信息。

标准名称：{standard_name}
患者诊断参考：{diagnosis}

文档内容：
{text[:8000]}

请提取以下结构化信息，以JSON格式输出：
{{
  "standard_name": "标准名称",
  "standard_code": "标准编号（T/CNAS XX-XXXX）",
  "nursing_assessment": "护理评估要点，包含：评估时机、评估内容、评估工具/量表，200-400字",
  "indications": ["适应症1", "适应症2", ...],
  "contraindications": ["禁忌证1", "禁忌证2", ...],
  "preparations": {{
    "drugs": "药物准备（名称、规格、剂量）",
    "equipment": "器械/物品清单（详细列举）",
    "patient_prep": "患者准备事项",
    "environment_prep": "环境准备事项"
  }},
  "operation_key_points": "操作要点（分步骤，含操作顺序、关键技术点、质量标准）",
  "complications": ["并发症1", "并发症2", ...],
  "intervention_measures": "各并发症的干预与处理措施",
  "precautions": "操作注意事项"
}}

要求：
1. 严格基于文档内容提取，不要臆造信息
2. 如某项内容文档中未提及，填写"文档未明确说明"
3. 操作要点需保留步骤序号
4. 输出纯JSON，不要有其他说明文字"""

    try:
        if os.environ.get("OPENAI_API_KEY"):
            import openai
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            result_text = response.choices[0].message.content
        elif os.environ.get("DEEPSEEK_API_KEY"):
            import openai
            client = openai.OpenAI(
                api_key=os.environ["DEEPSEEK_API_KEY"],
                base_url="https://api.deepseek.com"
            )
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            result_text = response.choices[0].message.content
        else:
            return None
        
        return json.loads(result_text)
    
    except Exception as e:
        print(f"[WARN] LLM提取失败: {e}，降级使用规则提取")
        return None


def analyze_multiple_standards(pdf_paths_or_texts, standard_names, diagnosis=""):
    """分析多个标准（用于有多个护理操作的情况）
    
    Args:
        pdf_paths_or_texts: PDF文件路径列表或文本列表
        standard_names: 标准名称列表
        diagnosis: 患者诊断
    
    Returns:
        合并后的分析结果列表
    """
    results = []
    
    for i, item in enumerate(pdf_paths_or_texts):
        std_name = standard_names[i] if i < len(standard_names) else f"标准{i+1}"
        print(f"\n[INFO] 分析标准 {i+1}/{len(pdf_paths_or_texts)}: {std_name}")
        
        # 判断是PDF路径还是文本
        if isinstance(item, str) and item.endswith('.pdf') and os.path.exists(item):
            text = extract_pdf_text(item)
        else:
            text = item  # 可能是网页文本
        
        # 结构化提取
        result = None
        if text:
            result = llm_structured_extract(text, std_name, diagnosis)
            if not result:
                result = rule_based_extract(text, std_name)
        
        if not result or not any([result.get("nursing_assessment"), result.get("indications")]):
            result = generate_standard_template(std_name, diagnosis)
        
        result["standard_name"] = std_name
        results.append(result)
    
    return results


def extract_complications_detailed(text, standard_name=""):
    """详细提取并发症及处理措施
    
    从标准文档中提取：
    1. 并发症名称列表
    2. 每个并发症的处理措施
    3. 预防要点
    """
    result = {
        "standard_name": standard_name,
        "complications": [],
        "prevention": "",
        "emergency_handling": ""
    }
    
    # 提取并发症章节
    comp_section = ""
    lines = text.split('\n')
    in_complication_section = False
    complication_keywords = ['并发症', '不良反应', '风险因素', '并发症及处理']
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # 检测并发症章节开始
        if any(kw in line_stripped for kw in complication_keywords):
            in_complication_section = True
            comp_section += line + '\n'
            continue
        
        # 检测章节结束（遇到新的章节标题）
        if in_complication_section:
            if re.match(r'^\d+[\.、]', line_stripped) and len(line_stripped) < 50:
                # 新的章节开始
                if not any(kw in line_stripped for kw in complication_keywords):
                    in_complication_section = False
            else:
                comp_section += line + '\n'
    
    # 如果没有找到并发症章节，尝试在整个文本中搜索
    if not comp_section:
        comp_match = re.search(r'(并发症|不良反应|风险因素)[^\n]*\n(.*?)(?=\n\d+[\.、]|$)', text, re.DOTALL)
        if comp_match:
            comp_section = comp_match.group(0)
    
    # 解析并发症列表
    if comp_section:
        # 提取并发症名称（通常是列表形式）
        comp_items = re.findall(r'[a-zA-Z\d\u4e00-\u9fff][）\)、\.．]([^\n]{3,60})', comp_section)
        if comp_items:
            result["complications"] = [item.strip() for item in comp_items]
        else:
            # 尝试按行提取
            for line in comp_section.split('\n'):
                line = line.strip()
                if len(line) >= 3 and len(line) <= 60 and not line.startswith('#'):
                    result["complications"].append(line)
        
        # 提取预防要点
        prevention_match = re.search(r'预防[^\n]*\n(.*?)(?=\n\d+[\.、]|$)', comp_section, re.DOTALL)
        if prevention_match:
            result["prevention"] = prevention_match.group(1).strip()[:500]
        
        # 提取应急处理
        emergency_match = re.search(r'应急[^\n]*\n(.*?)(?=\n\d+[\.、]|$)', comp_section, re.DOTALL)
        if emergency_match:
            result["emergency_handling"] = emergency_match.group(1).strip()[:500]
    
    return result


def generate_standard_template(standard_name, diagnosis):
    """当无法获取PDF/网页内容时，生成基于诊断的标准化模板"""
    
    # 根据标准名称推断内容
    templates = {
        "气管切开": {
            "nursing_assessment": "1.评估患者意识状态、呼吸功能、气道分泌物情况\n2.评估气管切开切口愈合情况\n3.评估气道通畅性\n4.评估套管固定情况（松紧度以容纳1-2指为宜）",
            "indications": ["气管切开术后患者", "需要长期气道管理者", "上气道梗阻需要气道维护者"],
            "contraindications": ["无绝对禁忌症", "凝血功能障碍需慎重操作"],
            "equipment": "吸痰管（型号适当）、无菌手套、无菌生理盐水、湿化装置、气管切开护理包、吸氧装置",
            "operation_key_points": "1.核对患者身份\n2.评估气道分泌物\n3.采用无菌技术进行气道吸引\n4.维护气管造瘘口清洁\n5.保持气道湿化",
            "complications": ["气道堵塞", "皮下气肿", "出血", "感染", "套管脱出"],
        },
        "氧气吸入": {
            "nursing_assessment": "1.评估患者呼吸频率、节律、深度\n2.SpO2监测\n3.评估意识状态\n4.评估吸氧装置通畅性",
            "indications": ["低氧血症（SpO2<95%）", "呼吸困难", "心肺功能不全"],
            "contraindications": ["面部创伤（面罩禁忌）"],
            "equipment": "氧气流量计、鼻导管或面罩、湿化瓶、蒸馏水",
            "operation_key_points": "1.核对医嘱（氧流量、吸氧方式）\n2.检查吸氧装置\n3.清洁鼻腔\n4.正确连接并固定\n5.记录开始时间",
            "complications": ["氧中毒", "气道干燥", "皮肤压力性损伤（面罩使用）"],
        },
    }
    
    # 匹配最佳模板
    matched_template = None
    for key, tmpl in templates.items():
        if key in standard_name or key in diagnosis:
            matched_template = tmpl
            break
    
    if not matched_template:
        matched_template = templates["氧气吸入"]  # 默认模板
    
    return {
        "standard_name": standard_name,
        "standard_code": "参见标准文件",
        "nursing_assessment": matched_template.get("nursing_assessment", ""),
        "indications": matched_template.get("indications", []),
        "contraindications": matched_template.get("contraindications", []),
        "preparations": {
            "drugs": matched_template.get("drugs", "遵医嘱准备相关药物"),
            "equipment": matched_template.get("equipment", "参见标准文件用物准备章节"),
            "patient_prep": "向患者及家属解释操作目的、方法及配合要点",
            "environment_prep": "清洁、安静、光线充足，温湿度适宜"
        },
        "operation_key_points": matched_template.get("operation_key_points", "参见标准文件操作步骤"),
        "complications": matched_template.get("complications", []),
        "intervention_measures": "发现并发症时立即停止操作，评估患者状态，必要时通知医生",
        "precautions": "严格执行无菌操作原则；操作前核查患者身份；操作后记录"
    }


def main():
    parser = argparse.ArgumentParser(description="护理操作PDF结构化分析")
    parser.add_argument("--pdf_path", help="PDF文件路径（单个）")
    parser.add_argument("--pdf_paths", nargs='+', help="PDF文件路径列表（多个）")
    parser.add_argument("--text_input", help="直接输入文本（替代PDF）")
    parser.add_argument("--standard_name", default="", help="标准名称（单个）")
    parser.add_argument("--standard_names", nargs='+', help="标准名称列表（多个）")
    parser.add_argument("--diagnosis", default="", help="患者诊断（辅助分析）")
    parser.add_argument("--output", default="", help="输出JSON文件路径")
    parser.add_argument("--output_dir", default="", help="输出目录（用于多个结果）")
    parser.add_argument("--extract_complications", action="store_true", help="详细提取并发症及处理措施")
    args = parser.parse_args()
    
    # 详细提取并发症模式
    if args.extract_complications and args.pdf_path:
        print(f"[INFO] 详细提取并发症: {args.pdf_path}")
        text = extract_pdf_text(args.pdf_path)
        result = extract_complications_detailed(text, args.standard_name)
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"[DONE] 并发症分析结果已保存: {args.output}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    # 多个PDF分析模式
    if args.pdf_paths:
        print(f"[INFO] 分析多个标准，共 {len(args.pdf_paths)} 个")
        standard_names = args.standard_names if args.standard_names else [f"标准{i+1}" for i in range(len(args.pdf_paths))]
        
        results = analyze_multiple_standards(
            args.pdf_paths,
            standard_names,
            diagnosis=args.diagnosis
        )
        
        # 保存结果
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            for i, result in enumerate(results):
                output_path = os.path.join(args.output_dir, f"analysis_{i+1}.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"[DONE] 分析结果 {i+1} 已保存: {output_path}")
            
            # 保存合并结果
            merged_path = os.path.join(args.output_dir, "analysis_merged.json")
            with open(merged_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"[DONE] 合并结果已保存: {merged_path}")
        elif args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"[DONE] 分析结果已保存: {args.output}")
        else:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        
        return
    
    # 单个PDF/文本分析模式（原有逻辑）
    text = ""
    if args.pdf_path and os.path.exists(args.pdf_path):
        print(f"[INFO] 提取PDF: {args.pdf_path}")
        text = extract_pdf_text(args.pdf_path)
    elif args.text_input:
        text = args.text_input
        print(f"[INFO] 使用输入文本，{len(text)} 字符")
    
    # 结构化提取
    result = None
    if text:
        print("[INFO] 尝试LLM结构化提取...")
        result = llm_structured_extract(text, args.standard_name, args.diagnosis)
        
        if not result:
            print("[INFO] 使用规则提取...")
            result = rule_based_extract(text, args.standard_name)
    
    if not result or not any([result.get("nursing_assessment"), result.get("indications")]):
        print("[INFO] 生成标准化模板...")
        result = generate_standard_template(args.standard_name, args.diagnosis)
    
    # 确保standard_name正确
    if args.standard_name:
        result["standard_name"] = args.standard_name
    
    # 输出
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[DONE] 分析结果已保存: {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return result


if __name__ == "__main__":
    main()
