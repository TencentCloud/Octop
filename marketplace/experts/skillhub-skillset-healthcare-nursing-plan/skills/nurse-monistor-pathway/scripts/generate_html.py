#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
护理监护计划HTML生成脚本 v3.0
功能增强：
  1. 量表支持多次记录（操作前/后、入院/出院等对比评估）
  2. 量表项目按指南标准扩展，正确计算总分，支持保存
  3. 护理宣教支持单独打印PDF
  4. 护理操作记录推荐日期基于临床路径时间轴预设
  5. 每日巡查登记表选择项支持多选，列宽可拖拽调节，可连续打印PDF
  6. 临床路径时间轴置顶
  7. 护理会诊、随访、不良事件完整登记表
"""

import argparse
import json
import os
from datetime import datetime, timedelta


def load_standards(standards_json_path):
    if standards_json_path and os.path.exists(standards_json_path):
        with open(standards_json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def get_patrol_frequency(nursing_level):
    levels = {
        "特级护理": {"frequency": "持续守护/每15-30分钟", "items": [
            "意识状态", "瞳孔变化", "生命体征（T/P/R/BP/SpO₂）",
            "皮肤情况", "管道通畅性", "引流液性状", "出入量记录", "用药反应"
        ]},
        "一级护理": {"frequency": "每小时至少一次", "items": [
            "意识状态", "生命体征（至少每4小时）", "皮肤受压情况",
            "管道固定与通畅", "静脉输液情况", "排泄情况", "安全防护"
        ]},
        "二级护理": {"frequency": "每2小时一次", "items": [
            "生命体征（每8小时）", "活动能力", "皮肤情况",
            "饮食情况", "排泄情况", "用药情况"
        ]},
        "三级护理": {"frequency": "每3小时一次", "items": [
            "生命体征（每日至少2次）", "饮食情况", "活动与休息",
            "用药情况", "情绪状态"
        ]}
    }
    return levels.get(nursing_level, levels["一级护理"])


def get_nursing_orders(diagnosis, nursing_level, standards):
    base_orders = {
        "特级护理": [
            "持续床旁守护，每15-30分钟记录一次生命体征",
            "禁食或按医嘱执行特殊饮食",
            "绝对卧床，保持床头抬高30°",
            "持续心电监护及SpO₂监测",
            "每日评估压力性损伤风险（Braden量表）",
            "建立特护记录单，详细记录24小时出入量",
        ],
        "一级护理": [
            "每小时巡视病房，观察病情变化",
            "每4小时测量生命体征（T、P、R、BP、SpO₂）",
            "协助生活护理（口腔护理、皮肤护理、床上擦浴）",
            "按医嘱执行半流质或流质饮食",
            "保持床单位整洁干燥，预防压力性损伤",
            "落实跌倒/坠床预防措施",
            "正确执行各项护理操作，并记录",
        ],
        "二级护理": [
            "每2小时巡视病房",
            "每8小时测量生命体征",
            "指导协助生活自理",
            "按医嘱执行普通饮食或治疗饮食",
            "健康宣教，指导患者及家属",
            "落实安全管理措施",
        ],
        "三级护理": [
            "每3小时巡视病房",
            "每日至少测量2次生命体征",
            "自理为主，护士提供指导",
            "普通饮食，健康宣教",
            "安全防护宣教",
        ]
    }
    orders = base_orders.get(nursing_level, base_orders["一级护理"])
    diagnosis_lower = diagnosis.lower()
    special_orders = []
    if any(kw in diagnosis_lower for kw in ["气管切开", "气管造口", "气道"]):
        special_orders = [
            "气道管理：每班评估气道通畅性，按需吸痰（分泌物黏稠时加强气道湿化）",
            "气管造瘘口护理：每日换药1-2次，保持局部清洁干燥",
            "气管套管固定：定期检查固定带松紧度（以插入1-2指为宜）",
            "气囊压力监测：每8小时监测一次，维持25-30cmH₂O",
        ]
    elif any(kw in diagnosis_lower for kw in ["化疗", "肿瘤", "癌"]):
        special_orders = [
            "化疗药物输注：全程监护，防止外渗，每30分钟观察穿刺点",
            "疼痛评估：使用NRS疼痛量表，每4小时评估一次",
            "化疗不良反应观察：监测恶心呕吐、骨髓抑制情况",
            "保护性隔离措施（必要时）",
        ]
    elif any(kw in diagnosis_lower for kw in ["骨折", "手术", "术后"]):
        special_orders = [
            "体位护理：保持患肢功能位，定时协助翻身",
            "切口观察：每班检查切口有无渗血渗液",
            "疼痛管理：术后疼痛评分，按医嘱执行镇痛",
            "早期功能锻炼：按康复计划指导床上主动/被动运动",
        ]
    elif any(kw in diagnosis_lower for kw in ["心肌梗死", "心衰", "心力衰竭"]):
        special_orders = [
            "持续心电监护，密切观察心律变化",
            "严格控制输液速度（20-30滴/分）",
            "每日监测体重和出入量",
            "限制活动，按心功能分级制定活动计划",
        ]
    return orders + special_orders


def get_supplies(diagnosis, standards):
    supplies = {"药物": [], "器械": [], "一次性耗材": []}
    for std in standards:
        if isinstance(std, dict):
            prep = std.get("preparations", {})
            if isinstance(prep, dict):
                if prep.get("drugs"):
                    supplies["药物"].append(prep["drugs"])
                if prep.get("equipment"):
                    supplies["器械"].append(prep["equipment"])
    supplies["一次性耗材"].extend(["无菌手套（适当型号）", "护理记录单", "棉签/纱布", "胶布/3M敷贴"])
    diagnosis_lower = diagnosis.lower()
    if any(kw in diagnosis_lower for kw in ["气管切开", "气道"]):
        supplies["器械"].extend(["气管切开护理包", "负压吸引装置", "气道湿化装置"])
        supplies["药物"].extend(["无菌生理盐水100mL", "气道湿化液"])
        supplies["一次性耗材"].extend(["吸痰管（12-14Fr）", "吸引管", "气管垫"])
    elif any(kw in diagnosis_lower for kw in ["静脉", "输液", "化疗"]):
        supplies["器械"].extend(["输液泵", "PICC换药包（必要时）"])
        supplies["一次性耗材"].extend(["留置针（22-24G）", "透明贴膜", "输液器"])
    return supplies


def generate_risk_list(diagnosis, pathway_days=7):
    """生成结构化的护理监护风险因素清单（列表式）"""
    base_risks = [
        {"name": "体温异常", "type": "生命体征监测", "stage": f"D1-D{pathway_days}", "monitor_value": "36.0-37.2℃", "level": "中风险", "intervention": "每4小时监测体温，物理降温", "handling": "体温>38.5℃立即通知医生，给予退热处理"},
        {"name": "心律失常", "type": "生命体征监测", "stage": f"D1-D{pathway_days}", "monitor_value": "P 60-100次/分", "level": "高风险", "intervention": "持续心电监护，每班记录", "handling": "发现频发室早/房颤/传导阻滞立即通知医生"},
        {"name": "血压波动", "type": "生命体征监测", "stage": f"D1-D{pathway_days}", "monitor_value": "BP 90-140/60-90mmHg", "level": "中风险", "intervention": "每4小时测量，记录趋势", "handling": "BP>160/100或<90/60立即通知医生"},
        {"name": "呼吸频率改变", "type": "生命体征监测", "stage": f"D1-D{pathway_days}", "monitor_value": "R 12-20次/分", "level": "高风险", "intervention": "持续观察呼吸频率/节律/深度", "handling": "R<8或>30次/分、呼吸困难立即通知医生"},
        {"name": "SpO2下降", "type": "生命体征监测", "stage": f"D1-D{pathway_days}", "monitor_value": "SpO2 >=95%", "level": "高风险", "intervention": "持续SpO2监测，吸氧", "handling": "SpO2<90%立即通知医生，加强氧疗"},
        {"name": "血常规异常", "type": "检验异常", "stage": f"D1,D3,D7", "monitor_value": "WBC 4-10x10^9/L，PLT 100-300x10^9/L", "level": "中风险", "intervention": "按医嘱复查血常规", "handling": "WBC<2或>20、PLT<50立即通知医生"},
        {"name": "电解质紊乱", "type": "检验异常", "stage": f"D1,D3,D7", "monitor_value": "K+ 3.5-5.5mmol/L，Na+ 135-145mmol/L", "level": "中风险", "intervention": "按医嘱复查电解质", "handling": "K+<3.0或>6.0、Na+<125或>155立即通知医生"},
        {"name": "药物不良反应", "type": "治疗相关", "stage": f"D1-D{pathway_days}", "monitor_value": "观察用药反应", "level": "中风险", "intervention": "用药前评估，用药中观察", "handling": "出现严重不良反应（皮疹/休克/呼吸困难）立即停药并通知医生"},
        {"name": "输液反应", "type": "治疗相关", "stage": f"D1-D{pathway_days}", "monitor_value": "观察穿刺点/滴速", "level": "中风险", "intervention": "定时巡视输液情况", "handling": "出现外渗/红肿/发热立即停止输液并通知医生"},
        {"name": "导管相关性感染", "type": "护理操作风险", "stage": f"D1-D{pathway_days}", "monitor_value": "穿刺点无红肿", "level": "高风险", "intervention": "严格无菌操作，定期换药", "handling": "出现红肿/渗液/发热立即通知医生"},
        {"name": "跌倒/坠床", "type": "护理操作风险", "stage": f"D1-D{pathway_days}", "monitor_value": "Morse评分>=45", "level": "高风险", "intervention": "床栏使用、防滑、陪护", "handling": "发生跌倒立即评估伤情，通知医生"},
        {"name": "压力性损伤", "type": "护理操作风险", "stage": f"D1-D{pathway_days}", "monitor_value": "Braden<=12分", "level": "高风险", "intervention": "每2小时翻身，减压敷料", "handling": "发现压疮按分期处理，通知伤口专科护士"},
        {"name": "误吸", "type": "护理操作风险", "stage": f"D1-D{pathway_days}", "monitor_value": "吞咽功能评估", "level": "高风险", "intervention": "进食时抬高床头30度，细嚼慢咽", "handling": "发生误吸立即清除口腔异物，吸氧，通知医生"},
    ]
    
    diagnosis_lower = diagnosis.lower()
    if any(kw in diagnosis_lower for kw in ["气管", "气道", "呼吸"]):
        base_risks.extend([
            {"name": "痰液堵塞气道", "type": "气道管理风险", "stage": f"D1-D{pathway_days}", "monitor_value": "痰液黏稠/量增多", "level": "高风险", "intervention": "加强气道湿化，按需吸痰", "handling": "立即清除分泌物，必要时更换套管"},
            {"name": "套管脱出", "type": "气道管理风险", "stage": f"D1-D{pathway_days}", "monitor_value": "固定带松紧度", "level": "高风险", "intervention": "每班检查固定带（容纳1-2指）", "handling": "立即通知医生，保持气道开放"},
            {"name": "气道出血", "type": "气道管理风险", "stage": f"D1-D{pathway_days}", "monitor_value": "吸痰时血性分泌物", "level": "中风险", "intervention": "轻柔吸痰，监测出血量", "handling": "大量出血时压迫止血，通知医生"},
            {"name": "皮下气肿", "type": "气道管理风险", "stage": f"D1-D3", "monitor_value": "颈部触诊捻发音", "level": "中风险", "intervention": "观察气肿范围，标记边界", "handling": "进行性加重时通知医生"},
        ])
    if any(kw in diagnosis_lower for kw in ["化疗", "肿瘤"]):
        base_risks.extend([
            {"name": "骨髓抑制", "type": "化疗相关", "stage": f"D1-D{pathway_days}", "monitor_value": "WBC<3x10^9/L或PLT<50x10^9/L", "level": "高风险", "intervention": "每周监测血常规，预防感染", "handling": "WBC<1或PLT<20立即通知医生，隔离防护"},
            {"name": "药物外渗", "type": "化疗相关", "stage": f"D1-D{pathway_days}", "monitor_value": "穿刺点无红肿/疼痛", "level": "高风险", "intervention": "每30分钟观察穿刺点", "handling": "立即停止输液，回抽药液，局部处理"},
            {"name": "恶心呕吐", "type": "化疗相关", "stage": f"D1-D5", "monitor_value": "CTCAE分级", "level": "中风险", "intervention": "化疗前预防性止吐", "handling": "严重呕吐给予止吐药，监测电解质"},
        ])
    if any(kw in diagnosis_lower for kw in ["糖尿病", "血糖"]):
        base_risks.extend([
            {"name": "低血糖", "type": "血糖管理", "stage": f"D1-D{pathway_days}", "monitor_value": "血糖<3.9mmol/L", "level": "高风险", "intervention": "定时监测血糖，备糖水/葡萄糖", "handling": "立即口服糖水/葡萄糖，意识不清者呼叫120"},
            {"name": "高血糖危象", "type": "血糖管理", "stage": f"D1-D{pathway_days}", "monitor_value": "血糖>13.9mmol/L", "level": "高风险", "intervention": "监测血糖，按医嘱调整胰岛素", "handling": "血糖>16.7或出现酮症立即通知医生"},
        ])
    return base_risks


def get_education_content(stage, diagnosis, symptoms="", medications="", examinations=""):
    diagnosis_lower = diagnosis.lower()
    is_airway = any(kw in diagnosis_lower for kw in ["气管切开", "气道", "呼吸", "肺"])
    is_cardiac = any(kw in diagnosis_lower for kw in ["心肌梗死", "心衰", "心力衰竭", "心脏", "冠心病"])
    is_chemo = any(kw in diagnosis_lower for kw in ["化疗", "肿瘤", "癌"])
    is_surgery = any(kw in diagnosis_lower for kw in ["手术", "术后", "骨折"])
    is_diabetes = any(kw in diagnosis_lower for kw in ["糖尿病", "血糖"])

    if stage == "admission":
        items = [
            {"title": "病区环境与设施", "content": "介绍病区环境布局、呼叫铃使用方法、洗手间及病区走廊规则；告知探视制度（探视时间、探视人数限制）；介绍主管护士及主治医生。"},
            {"title": "安全防护要求", "content": "床头摇高/降低操作说明；24小时留陪要求；离床活动需告知护士；贵重物品保管提示；防坠床措施（床栏使用）。"},
            {"title": f"「{diagnosis}」疾病知识", "content": f"{'气管切开术是建立人工气道的手术，术后需要持续气道管理，包括吸痰、气道湿化和套管护理。' if is_airway else ''}{'心脏疾病需严格控制活动量，监测心率、血压、水肿情况，限制水盐摄入。' if is_cardiac else ''}{'化疗药物通过静脉给药，全疗程约数天，需监测白细胞、血小板等血液指标。' if is_chemo else ''}{'术后需关注切口愈合、引流管情况，按计划开展康复锻炼。' if is_surgery else ''}{'糖尿病管理核心：监测血糖、规律用药（胰岛素/口服降糖药）、控制饮食。' if is_diabetes else f'告知「{diagnosis}」的主要病理机制、常见症状和治疗方向。'}"},
            {"title": "入院检查配合", "content": f"{'完成血常规、生化、血气分析、胸部影像学检查。' if is_airway else ''}{'完成心电图、超声心动图、心肌酶等检查。' if is_cardiac else ''}{'完成血常规（关注WBC/PLT）、生化全套、肿瘤标志物、影像学检查。' if is_chemo else ''}{'完成X线/CT影像检查、血液检查（血型、凝血功能）等。' if is_surgery else f'配合完成「{diagnosis}」相关的各项必要检查，检查前禁食或特殊要求遵医嘱执行。'}"},
            {"title": "饮食与作息要求", "content": f"{'气管切开患者经口进食需评估吞咽功能，必要时鼻饲饮食；高蛋白高热量食物促进伤口愈合。' if is_airway else ''}{'心脏病患者低盐低脂饮食（盐<3g/天），限制液体摄入量（<1500ml/天），保持大便通畅。' if is_cardiac else ''}{'化疗期间进食清淡易消化食物，少量多餐；化疗后24-48小时内适量补液预防肾损伤。' if is_chemo else ''}{'糖尿病患者严格控制主食量（碳水化合物占总热量50-55%），每餐定量定时，监测餐前餐后血糖。' if is_diabetes else '按医嘱执行治疗饮食；充足休息，保持情绪平稳。'}"},
        ]
        if medications:
            items.append({"title": "入院用药说明", "content": f"目前用药：{medications}。服药时间及方式遵医嘱；出现不适及时告知护士；不得自行停药或调整剂量。"})
        return items

    elif stage == "inhospital":
        items = [
            {"title": f"「{diagnosis}」护理配合要点", "content": f"{'吸痰时放松配合，避免用力咳嗽或屏气；气道湿化装置保持运行；套管护理时保持头部不动。' if is_airway else ''}{'心脏监护仪报警时保持冷静，立即告知护士；活动限于床旁或病室内；出现胸闷、憋气立即卧床告知医护。' if is_cardiac else ''}{'化疗输液期间如感到穿刺部位疼痛、肿胀立即告知护士（防药物外渗）；恶心呕吐时采取侧卧位，告知用止吐药。' if is_chemo else ''}{'术后按计划进行功能锻炼，切口疼痛可告知护士评估镇痛需求。' if is_surgery else f'积极配合「{diagnosis}」相关治疗和护理操作，有不适及时告知。'}"},
            {"title": "用药管理与监测", "content": f"{'气道管理用药：雾化吸入药物（布地奈德/异丙托溴铵）在吸痰后使用效果更好；抗生素按时使用。' if is_airway else ''}{'心脏用药：利尿剂（呋塞米等）需监测尿量，每日尿量>1000ml为正常；ACEI/ARB类药物注意低血压和干咳副作用。' if is_cardiac else ''}{'化疗药物：如出现脱发属正常现象；口腔溃疡时用生理盐水漱口；白细胞降低时避免人群聚集。' if is_chemo else ''}{'糖尿病用药：胰岛素注射时间、部位按计划执行；口服降糖药餐前或餐时服用遵医嘱；血糖<3.9mmol/L立即告知。' if is_diabetes else f'所有用药严格遵医嘱执行，「{medications if medications else diagnosis}」相关用药不得自行停药。'}"},
            {"title": "检查检验配合", "content": f"{'定期复查血气分析（监测氧合指数）、血常规、痰培养（指导抗生素选择）、胸部CT。' if is_airway else ''}{'心功能监测：心电图每天或按需；BNP/NT-proBNP、心肌酶定期复查；超声心动评估心功能。' if is_cardiac else ''}{'血常规（每周1-2次）关注白细胞计数；肝肾功能评估化疗耐受性；肿瘤标志物定期复查。' if is_chemo else ''}{'血糖监测：空腹+三餐后2小时共4次/天；HbA1c每3个月查一次；定期检查尿微量白蛋白、眼底、足部感觉。' if is_diabetes else f'配合「{examinations if examinations else '必要的'}」检查，检查前特殊要求（禁食/备皮等）提前告知。'}"},
            {"title": "预防并发症", "content": f"{'气道堵塞预防：气道湿化持续进行；痰液黏稠时增加湿化量；定期翻身拍背促进痰液排出。' if is_airway else ''}{'深静脉血栓预防：卧床期间定时踝泵运动（每次20-30个，每2小时一次）；必要时穿弹力袜。' if is_cardiac or is_surgery else ''}{'感染预防：病室每日通风2次；手卫生；减少探视人员；白细胞减少期间戴口罩。' if is_chemo else ''}{'压力性损伤预防：每2小时翻身一次；骨突处使用减压敷料；保持皮肤清洁干燥。'}"},
            {"title": "心理支持与情绪管理", "content": f"「{diagnosis}」治疗过程中出现焦虑担忧是正常反应。可通过深呼吸放松、听音乐、与家人交流等方式缓解情绪。如情绪低落持续超过2周，可申请心理科会诊。家属的陪伴和支持对患者康复非常重要。"},
        ]
        return items

    else:  # discharge
        items = [
            {"title": "出院带药指导", "content": f"{'出院带药可能包括：气道湿化液、抗生素、止痰药（按医嘱）。居家气管切开护理需提前接受培训。' if is_airway else ''}{'心脏病带药：抗血小板药物（阿司匹林）不可随意停药；ACEI/ARB；β受体阻滞剂。出现严重低血压、心律不齐立即就诊。' if is_cardiac else ''}{'化疗间期带药：止吐药、升白细胞药（G-CSF）；口腔护理液；下次化疗时间遵医嘱。' if is_chemo else ''}{'糖尿病带药：胰岛素储存（未开封冷藏，开封后室温25℃以下保存28天）；血糖监测设备及耗材。' if is_diabetes else f'出院带药严格按医嘱服用，「{medications if medications else diagnosis}」相关药物不可自行停药。'}"},
            {"title": "居家自我管理", "content": f"{'居家气管切开护理：每日换药（生理盐水清洁造瘘口）；气管套管固定检查；痰液观察（颜色/黏稠度）；备好吸引器；发现呼吸困难立即就诊。' if is_airway else ''}{'心脏病居家：每日测量体重（增加>2kg/天提示水肿加重，就诊）；低盐饮食；限制剧烈活动；自测脉搏。' if is_cardiac else ''}{'化疗间期：监测体温（>38℃立即就诊，可能感染）；避免生食；外出戴口罩；下次化疗前1天复查血常规。' if is_chemo else ''}{'糖尿病居家：每日监测血糖（空腹+餐后）；足部检查（皮肤完整性、感觉）；规律运动（每次30分钟中等强度）；戒烟限酒。' if is_diabetes else f'「{diagnosis}」出院后继续执行居家护理计划，注意观察病情变化。'}"},
            {"title": "复查计划", "content": f"{'气管切开患者出院后1周、1个月、3个月门诊复查；由耳鼻喉科/外科评估气管套管拔除时机。' if is_airway else ''}{'心脏病出院后1周、1个月门诊复查；复查心电图、BNP、肝肾功能及电解质。' if is_cardiac else ''}{'下次化疗时间遵医嘱（一般21-28天为一个周期）；每次化疗前完成血常规+生化检查。' if is_chemo else ''}{'糖尿病3个月复查HbA1c；每年全面检查（眼底/肾功/下肢血管/神经）。' if is_diabetes else f'按医嘱定期门诊复查「{diagnosis}」相关指标。'}"},
            {"title": "紧急情况处理", "content": f"{'气管切开紧急情况：①套管脱出→立即保持气道开放，呼叫120；②大量出血→用纱布压迫，呼叫120；③痰液堵塞/呼吸困难→立即就近就诊。' if is_airway else ''}{'心脏急症：胸痛/胸闷持续超过20分钟→立即拨打120，舌下含服硝酸甘油（有备药时）；严重水肿/端坐呼吸→立即就诊。' if is_cardiac else ''}{'化疗急症：高热（>38.5℃）→立即就诊，不要自行退烧；严重口腔溃疡无法进食→就诊；皮疹/过敏反应→立即就诊。' if is_chemo else ''}{'低血糖急救：意识清醒时口服糖水/葡萄糖片；意识不清不可经口喂食→呼叫120。' if is_diabetes else '出现病情急剧变化、严重不适立即就近就医，必要时拨打120。'}"},
            {"title": "康复与随访", "content": f"出院后{7 if is_surgery or is_airway else 14}天内电话随访；按随访计划完成门诊复诊；有问题可通过病区电话咨询责任护士。"},
        ]
        if examinations:
            items.append({"title": "出院后检查追踪", "content": f"需追踪的检查结果：{examinations}。复查结果建议保存，复诊时携带。"})
        return items


def generate_education_items_detailed(items):
    html = ""
    for item in items:
        if isinstance(item, dict):
            html += f'''<div style="margin-bottom:8px;border:1px solid #dce4ef;border-radius:5px;overflow:hidden">
              <div style="background:#e8f0fa;padding:5px 10px;font-size:12px;font-weight:700;color:#0d3d7a">📌 {item["title"]}</div>
              <div style="padding:6px 10px;font-size:12px;line-height:1.7;color:#2c3e50">{item["content"]}</div>
            </div>'''
        else:
            html += f'<div style="padding:3px 0;font-size:12px">• {item}</div>'
    return html


def get_patrol_select_options():
    return {
        "意识状态": ["清醒", "嗜睡", "昏睡", "浅昏迷", "深昏迷"],
        "瞳孔变化": ["等大等圆/对光反射灵敏", "左右不等大", "对光反射迟钝", "对光反射消失"],
        "皮肤情况": ["完整无异常", "局部潮红", "破损/压疮", "水肿"],
        "皮肤受压情况": ["完整无异常", "局部潮红", "破损/压疮I期", "破损/压疮II期及以上"],
        "管道情况": ["固定通畅", "固定松动", "引流不畅", "脱出"],
        "管道固定与通畅": ["固定通畅", "固定松动", "引流不畅", "脱出"],
        "呼吸情况": ["平稳", "呼吸急促", "呼吸困难", "呼吸暂停"],
        "SpO₂": ["≥95%", "90-94%", "85-89%", "<85%"],
        "排泄情况": ["正常", "少尿/无尿", "腹泻", "便秘", "失禁"],
        "静脉输液情况": ["输液通畅无渗出", "滴速偏快/偏慢", "局部渗出肿胀", "已停止输液"],
        "安全防护": ["床栏已升起", "约束在位", "呼叫铃可及", "有跌倒风险"],
        "生命体征（至少每4小时）": ["正常范围", "体温异常", "血压异常", "心率异常", "SpO₂下降"],
        "生命体征（每8小时）": ["正常范围", "体温异常", "血压异常", "心率异常"],
        "生命体征（每日至少2次）": ["正常范围", "体温异常", "血压异常"],
        "活动能力": ["自主活动", "需协助", "卧床不起", "制动"],
        "饮食情况": ["正常进食", "进食量少", "禁食中", "鼻饲中"],
        "用药情况": ["按时服药", "漏服", "拒服", "不良反应"],
        "情绪状态": ["平稳", "焦虑", "抑郁", "激动"],
        "引流液性状": ["正常色量", "引流量增多", "颜色异常", "引流停止"],
        "出入量记录": ["已记录", "未完成"],
        "用药反应": ["无不适", "恶心/呕吐", "皮疹/过敏", "低血压"],
    }


def get_daily_focus(day, total_days, diagnosis):
    if day == 1:
        return "入院评估；健康宣教；操作准备"
    elif day <= 3:
        return "重点监护；操作执行；并发症预防"
    elif day <= total_days // 2:
        return "病情观察；康复指导；并发症监控"
    elif day <= total_days - 1:
        return "康复护理；自理能力训练；出院准备"
    else:
        return "出院评估；出院宣教；随访预约"


def generate_pathway_rows(pathway_rows, diagnosis, nursing_level):
    care_items = [
        ("生命体征监测", "✓", "✓", "✓"),
        ("护理评估（量表）", "✓", "·", "·"),
        ("护理宣教", "入院", "住院", "出院"),
        ("护理操作执行", "·", "✓", "·"),
        ("并发症预防", "✓", "✓", "✓"),
        ("心理护理", "✓", "按需", "·"),
        ("功能锻炼指导", "·", "✓", "✓"),
        ("出院准备", "·", "·", "✓"),
    ]
    rows = ""
    for item_name, early, mid, late in care_items:
        rows += f'<tr><td style="font-weight:600">{item_name}</td>'
        for r in pathway_rows:
            day = r["day"]
            total = len(pathway_rows)
            if day == 1:
                mark = early
            elif day >= total:
                mark = late
            else:
                mark = mid
            color = "#1a5fa8" if mark == "✓" else ("#e67e22" if mark not in ["·", ""] else "#ccc")
            rows += f'<td style="text-align:center;color:{color};font-size:13px">{mark}</td>'
        rows += '</tr>'
    return rows


def generate_care_plan_html(
    diagnosis,
    symptoms="",
    medications="",
    examinations="",
    patient_name="（患者姓名）",
    nursing_level="一级护理",
    pathway_days=7,
    standards=None,
    creator="护士",
    department="护理单元"
):
    if standards is None:
        standards = []

    now = datetime.now()
    admit_date = now.strftime("%Y年%m月%d日")

    patrol_info = get_patrol_frequency(nursing_level)
    nursing_orders = get_nursing_orders(diagnosis, nursing_level, standards)
    supplies = get_supplies(diagnosis, standards)
    risks = generate_risk_list(diagnosis, pathway_days)

    std_refs = []
    for std in standards:
        if isinstance(std, dict):
            std_refs.append(f"{std.get('standard_code', '')} {std.get('standard_name', '')}")
    std_refs_html = " | ".join(std_refs) if std_refs else "中华护理学会团体标准"

    patrol_times = {
        "特级护理": ["00:00", "01:00", "02:00", "03:00", "04:00", "05:00",
                     "06:00", "07:00", "08:00", "09:00", "10:00", "11:00",
                     "12:00", "13:00", "14:00", "15:00", "16:00", "17:00",
                     "18:00", "19:00", "20:00", "21:00", "22:00", "23:00"],
        "一级护理": ["06:00", "08:00", "10:00", "12:00", "14:00", "16:00",
                     "18:00", "20:00", "22:00", "00:00", "02:00", "04:00"],
        "二级护理": ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00", "00:00", "03:00"],
        "三级护理": ["07:00", "11:00", "15:00", "19:00", "23:00"],
    }
    times = patrol_times.get(nursing_level, patrol_times["一级护理"])

    pathway_rows_data = []
    for day in range(1, min(pathway_days + 1, 15)):
        date = now + timedelta(days=day - 1)
        pathway_rows_data.append({
            "day": day,
            "date": date.strftime("%m/%d"),
            "focus": get_daily_focus(day, pathway_days, diagnosis),
        })

    assessment_content = ""
    operation_points = []

    for std in standards:
        if isinstance(std, dict):
            if std.get("nursing_assessment"):
                assessment_content += f"\n<h4>【{std.get('standard_name', '')}】评估要点</h4>\n"
                assessment_content += f"<p>{std.get('nursing_assessment', '').replace(chr(10), '<br>')}</p>"

            if std.get("operation_key_points"):
                operation_points.append({
                    "name": std.get("standard_name", ""),
                    "code": std.get("standard_code", ""),
                    "indications": std.get("indications", []),
                    "contraindications": std.get("contraindications", []),
                    "preparations": std.get("preparations", {}),
                    "key_points": std.get("operation_key_points", ""),
                    "complications": std.get("complications", []),
                    "interventions": std.get("intervention_measures", ""),
                    "precautions": std.get("precautions", ""),
                })

    if not assessment_content:
        assessment_content = f"""
        <p>1. <strong>基础评估</strong>：评估患者生命体征、意识状态、自理能力</p>
        <p>2. <strong>专科评估</strong>：针对「{diagnosis}」进行专科护理评估</p>
        <p>3. <strong>风险评估</strong>：Braden压力性损伤风险量表、跌倒风险评估（Morse量表）、疼痛NRS评分、营养风险筛查（NRS2002）</p>
        <p>4. <strong>心理评估</strong>：评估患者及家属的心理状态，制定针对性宣教计划</p>
        """

    select_options = get_patrol_select_options()
    patrol_items_display = patrol_info['items'][:6]

    edu_admission = get_education_content("admission", diagnosis, symptoms, medications, examinations)
    edu_inhospital = get_education_content("inhospital", diagnosis, symptoms, medications, examinations)
    edu_discharge = get_education_content("discharge", diagnosis, symptoms, medications, examinations)

    consultations = [
        ("常规护理会诊", "专科护理评估与指导", "入院48小时内", "责任护士"),
        ("营养支持护理会诊", "营养风险评估（NRS2002≥3分触发）与营养支持干预", "NRS2002≥3分时", "营养科护士"),
        ("伤口造口护理会诊", "皮肤/切口/造口护理方案制定", "按需", "伤口造口专科护士"),
        ("心理护理会诊", "患者/家属心理支持与干预", "按需", "心理科"),
    ]
    diagnosis_lower = diagnosis.lower()
    if any(kw in diagnosis_lower for kw in ["气管", "呼吸", "肺"]):
        consultations.append(("呼吸专科护理会诊", "气道管理方案优化与呼吸治疗", "入院后评估", "呼吸治疗师"))
    if any(kw in diagnosis_lower for kw in ["化疗", "肿瘤"]):
        consultations.append(("肿瘤专科护理会诊", "化疗护理方案与静脉通路管理", "化疗前", "肿瘤专科护士"))
    if any(kw in diagnosis_lower for kw in ["糖尿病", "血糖"]):
        consultations.append(("糖尿病专科护理会诊", "血糖管理方案与胰岛素使用指导", "入院后", "内分泌专科护士"))

    followup_list = [
        ("出院后第1周", "电话随访", f"体温、脉搏、呼吸、血压、SpO₂等生命体征监测情况；「{diagnosis}」症状变化；用药依从性；居家护理执行情况；有无不适或并发症迹象"),
        ("出院后第2周", "电话/门诊", f"复查结果（血常规、生化等）回顾；康复进展评估；居家护理情况；{'气道/套管情况评估' if any(kw in diagnosis_lower for kw in ['气管','气道']) else '饮食与活动情况'}"),
        ("出院后1个月", "门诊复诊", f"全面评估恢复情况（门诊体检+检验）；药物疗效评估；调整护理指导计划；{'气管套管拔管评估' if any(kw in diagnosis_lower for kw in ['气管']) else '并发症筛查'}"),
        ("出院后3个月", "定期随访", f"长期预后评估；{'HbA1c检查、糖尿病并发症筛查' if any(kw in diagnosis_lower for kw in ['糖尿病']) else '生活质量评估'}；健康行为指导与自我管理能力评估"),
    ]

    default_op = {
        "name": "通用护理操作规范",
        "code": "中华护理学会团体标准",
        "indications": ["按医嘱执行护理操作"],
        "contraindications": ["参照具体操作标准"],
        "preparations": {"drugs": "遵医嘱准备", "equipment": "按操作需要准备"},
        "key_points": "核对患者身份（两种以上方式核对）\n告知患者/家属操作目的及配合要点\n洗手/手卫生（七步洗手法）\n准备用物（按医嘱）\n执行操作（严格无菌原则）\n操作后评估效果\n操作后记录\n整理床单位及用物处置",
        "complications": ["操作相关并发症"],
        "interventions": "发现异常立即停止操作，通知医生，实施对症处理。",
        "precautions": "严格执行核查制度，遵循无菌操作原则，操作前后进行手卫生。",
    }
    if not operation_points:
        operation_points = [default_op]

    patrol_items_js = json.dumps(patrol_items_display, ensure_ascii=False)
    select_options_js = json.dumps(select_options, ensure_ascii=False)
    consultations_js = json.dumps([
        {"type": c[0], "purpose": c[1], "timing": c[2], "dept": c[3]}
        for c in consultations
    ], ensure_ascii=False)
    followup_js = json.dumps([
        {"timing": f[0], "method": f[1], "content": f[2]}
        for f in followup_list
    ], ensure_ascii=False)
    pathway_rows_js = json.dumps(pathway_rows_data, ensure_ascii=False)

    # 量表数据（支持多次记录）
    scale_definitions = get_scale_definitions()

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>护理监护计划 - {patient_name} - {diagnosis}</title>
<style>
  :root {{
    --primary: #1a5fa8;
    --primary-light: #e8f0fa;
    --primary-dark: #0d3d7a;
    --secondary: #2e8b57;
    --secondary-light: #e8f5ee;
    --warning: #e67e22;
    --warning-light: #fef5e7;
    --danger: #c0392b;
    --danger-light: #fdf0ef;
    --neutral: #5d6d7e;
    --border: #dce4ef;
    --text: #2c3e50;
    --text-light: #7f8c8d;
    --bg: #f4f7fc;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: var(--text);
    background: var(--bg);
    line-height: 1.6;
  }}
  @media print {{
    body {{ background: white; font-size: 11px; }}
    .no-print {{ display: none !important; }}
    .section {{ break-inside: avoid; page-break-inside: avoid; }}
    .page-break {{ page-break-before: always; }}
    .modal-overlay {{ display: none !important; }}
  }}
  /* ===== 护理记录单打印样式 ===== */
  @media print {{
    .patrol-printable {{ font-size: 10px; }}
    .patrol-printable th {{ font-size: 9px; padding: 3px 4px; }}
    .patrol-printable td {{ font-size: 9px; padding: 2px 4px; }}
    .patrol-printable .checkbox-col {{ display: inline-block; font-size: 8px; }}
  }}
  /* ===== 宣教打印样式 ===== */
  @media print.edu-print {{ 
    body * {{ display: none !important; }}
    .edu-printable, .edu-printable * {{ display: block !important; }}
    .edu-printable {{ position: absolute; top: 0; left: 0; width: 100%; background: white; }}
    .edu-card {{ break-inside: avoid; page-break-inside: avoid; }}
  }}
  .plan-header {{
    background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary) 100%);
    color: white; padding: 16px 24px;
    display: flex; justify-content: space-between; align-items: center;
  }}
  .plan-header h1 {{ font-size: 20px; font-weight: 700; letter-spacing: 2px; }}
  .plan-header .subtitle {{ font-size: 12px; opacity: 0.85; margin-top: 3px; }}
  .plan-header .header-btns {{ display:flex; gap:8px; }}
  .hdr-btn {{
    background: rgba(255,255,255,0.2); color: white;
    border: 1px solid rgba(255,255,255,0.4); padding: 5px 14px;
    border-radius: 4px; cursor: pointer; font-size: 12px;
  }}
  .hdr-btn:hover {{ background: rgba(255,255,255,0.35); }}
  .patient-card {{
    background: white; border-left: 4px solid var(--primary);
    margin: 12px 16px; padding: 12px 16px; border-radius: 0 8px 8px 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px;
  }}
  .info-label {{ font-size: 10px; color: var(--text-light); text-transform: uppercase; letter-spacing: 0.5px; }}
  .info-value {{ font-size: 13px; font-weight: 600; color: var(--primary-dark); margin-top: 2px; }}
  .ref-standards {{
    font-size: 11px; color: var(--text-light);
    border-top: 1px solid var(--border); padding-top: 6px; margin-top: 4px; grid-column: 1 / -1;
  }}
  .content {{ padding: 0 16px 24px; }}
  .section {{
    background: white; border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07); margin-bottom: 14px; overflow: hidden;
  }}
  .section-header {{
    background: var(--primary); color: white; padding: 9px 14px;
    font-size: 14px; font-weight: 700; display: flex; align-items: center; gap: 8px;
  }}
  .section-num {{
    background: rgba(255,255,255,0.25); border-radius: 50%;
    width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
    font-size: 11px;
  }}
  .section-body {{ padding: 14px; }}
  .sub-header {{
    background: var(--primary-light); border-left: 3px solid var(--primary);
    padding: 6px 10px; font-size: 13px; font-weight: 600;
    color: var(--primary-dark); margin: 10px 0 8px; border-radius: 0 4px 4px 0;
  }}
  .sub-header.green {{ background: var(--secondary-light); border-left-color: var(--secondary); color: var(--secondary); }}
  .sub-header.orange {{ background: var(--warning-light); border-left-color: var(--warning); color: var(--warning); }}
  .sub-header.red {{ background: var(--danger-light); border-left-color: var(--danger); color: var(--danger); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{
    background: var(--primary-light); color: var(--primary-dark);
    font-weight: 600; padding: 7px 8px; text-align: left; border: 1px solid var(--border);
  }}
  td {{ padding: 6px 8px; border: 1px solid var(--border); vertical-align: top; }}
  tr:nth-child(even) td {{ background: #fafbfd; }}
  tr:hover td {{ background: #eef4ff; }}
  select {{
    width: 100%; border: 1px solid #c5d5e8; border-radius: 3px;
    padding: 3px 5px; font-size: 11px; background: white; color: var(--text);
    cursor: pointer;
  }}
  select:focus {{ outline: 1px solid var(--primary); }}
  input[type=text], textarea {{
    width: 100%; border: 1px solid #c5d5e8; border-radius: 3px;
    padding: 3px 5px; font-size: 11px; resize: vertical;
  }}
  input[type=text]:focus, textarea:focus {{ outline: 1px solid var(--primary); }}
  .checklist-item {{
    display: flex; align-items: flex-start; gap: 8px;
    padding: 4px 0; border-bottom: 1px dashed var(--border);
  }}
  .checklist-item:last-child {{ border-bottom: none; }}
  .checklist-item input[type=checkbox] {{
    margin-top: 2px; width: 14px; height: 14px;
    cursor: pointer; accent-color: var(--primary);
  }}
  .checklist-item label {{ cursor: pointer; flex: 1; }}
  .risk-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }}
  .risk-card {{ border: 1px solid var(--border); border-radius: 6px; padding: 10px; }}
  .risk-card-title {{ font-weight: 600; font-size: 12px; color: var(--primary-dark); margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid var(--border); }}
  .risk-item {{ display: flex; align-items: center; gap: 6px; padding: 2px 0; font-size: 12px; }}
  .risk-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--primary); flex-shrink: 0; }}
  .pathway-timeline {{ overflow-x: auto; padding-bottom: 4px; }}
  .pathway-timeline table {{ min-width: 600px; }}
  .edu-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
  @media (max-width: 750px) {{ .edu-grid {{ grid-template-columns: 1fr; }} }}
  .edu-card {{ border-radius: 6px; padding: 12px; border: 1px solid var(--border); }}
  .edu-card-title {{ font-weight: 700; font-size: 13px; margin-bottom: 8px; padding-bottom: 4px; border-bottom: 2px solid; }}
  .edu-card.admission {{ border-top: 3px solid var(--primary); }}
  .edu-card.admission .edu-card-title {{ color: var(--primary); border-bottom-color: var(--primary); }}
  .edu-card.inhospital {{ border-top: 3px solid var(--secondary); }}
  .edu-card.inhospital .edu-card-title {{ color: var(--secondary); border-bottom-color: var(--secondary); }}
  .edu-card.discharge {{ border-top: 3px solid var(--warning); }}
  .edu-card.discharge .edu-card-title {{ color: var(--warning); border-bottom-color: var(--warning); }}
  .std-card {{ border: 1px solid var(--border); border-radius: 6px; margin-bottom: 10px; overflow: hidden; }}
  .std-card-header {{
    background: var(--primary-light); padding: 8px 12px; font-weight: 700; font-size: 13px;
    color: var(--primary-dark); display: flex; justify-content: space-between; align-items: center;
  }}
  .std-card-badge {{ font-size: 11px; background: var(--primary); color: white; padding: 2px 8px; border-radius: 10px; }}
  .std-card-body {{ padding: 12px; }}
  .tag-list {{ display: flex; flex-wrap: wrap; gap: 5px; margin: 4px 0; }}
  .tag {{ font-size: 11px; padding: 2px 7px; border-radius: 10px; border: 1px solid var(--border); }}
  .tag.green {{ background: var(--secondary-light); color: var(--secondary); border-color: var(--secondary); }}
  .tag.red {{ background: var(--danger-light); color: var(--danger); border-color: var(--danger); }}
  .tag.blue {{ background: var(--primary-light); color: var(--primary); border-color: var(--primary); }}
  .comp-table th {{ background: #fff3cd; color: #7d5a00; }}
  .sign-row {{ display: flex; gap: 20px; margin-top: 8px; }}
  .sign-box {{ flex: 1; border-top: 1px solid var(--border); padding-top: 4px; font-size: 11px; color: var(--text-light); text-align: center; }}
  .btn {{
    display: inline-block; padding: 5px 12px; border-radius: 4px; cursor: pointer;
    font-size: 12px; border: none; font-family: inherit;
  }}
  .btn-primary {{ background: var(--primary); color: white; }}
  .btn-primary:hover {{ background: var(--primary-dark); }}
  .btn-success {{ background: var(--secondary); color: white; }}
  .btn-success:hover {{ background: #236b43; }}
  .btn-warning {{ background: var(--warning); color: white; }}
  .btn-danger {{ background: var(--danger); color: white; }}
  .btn-outline {{ background: white; color: var(--primary); border: 1px solid var(--primary); }}
  .btn-outline:hover {{ background: var(--primary-light); }}
  .btn-sm {{ padding: 3px 8px; font-size: 11px; }}
  /* 日期导航 */
  .date-nav {{
    display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
    background: var(--primary-light); padding: 8px 12px; border-radius: 6px;
  }}
  .date-nav label {{ font-size: 12px; font-weight: 600; color: var(--primary-dark); }}
  .date-nav input[type=date] {{
    border: 1px solid var(--border); border-radius: 4px; padding: 4px 8px;
    font-size: 12px; width: auto;
  }}
  .date-nav .save-status {{ font-size: 11px; color: var(--secondary); margin-left: auto; }}
  /* 模态框 */
  .modal-overlay {{
    display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.55); z-index: 9000; overflow-y: auto;
  }}
  .modal-overlay.active {{ display: flex; align-items: flex-start; justify-content: center; padding: 20px; }}
  .modal-box {{
    background: white; border-radius: 10px; width: 100%; max-width: 680px;
    margin: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.25);
    max-height: 90vh; overflow-y: auto;
  }}
  .modal-header {{
    background: var(--primary); color: white; padding: 12px 18px;
    border-radius: 10px 10px 0 0; display: flex; justify-content: space-between; align-items: center;
    position: sticky; top: 0; z-index: 10;
  }}
  .modal-header h3 {{ font-size: 15px; font-weight: 700; }}
  .modal-close {{ background: none; border: none; color: white; font-size: 20px; cursor: pointer; line-height: 1; }}
  .modal-body {{ padding: 16px; }}
  .modal-footer {{ padding: 12px 16px; border-top: 1px solid var(--border); display: flex; gap: 8px; justify-content: flex-end; }}
  .form-group {{ margin-bottom: 12px; }}
  .form-group label {{ display: block; font-size: 12px; font-weight: 600; color: var(--primary-dark); margin-bottom: 4px; }}
  .form-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  @media (max-width: 500px) {{ .form-row {{ grid-template-columns: 1fr; }} }}
  /* 量表 */
  .scale-card {{
    border: 1px solid var(--border); border-radius: 6px; margin-bottom: 10px; overflow: hidden;
  }}
  .scale-card-header {{
    background: #eef4ff; padding: 8px 12px; cursor: pointer;
    display: flex; justify-content: space-between; align-items: center;
    font-size: 13px; font-weight: 600; color: var(--primary-dark);
  }}
  .scale-card-header:hover {{ background: #d9e8ff; }}
  .scale-card-body {{ padding: 12px; display: none; }}
  .scale-card-body.open {{ display: block; }}
  .scale-item {{ display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px dashed var(--border); font-size: 12px; }}
  .scale-item:last-child {{ border-bottom: none; }}
  .scale-item-label {{ flex: 1; color: var(--text); }}
  .scale-item-score {{ min-width: 70px; text-align: right; }}
  .scale-item-score select {{ width: 70px; }}
  .scale-total {{
    background: var(--primary-light); padding: 6px 10px; border-radius: 4px; margin-top: 8px;
    font-weight: 700; font-size: 13px; color: var(--primary-dark);
    display: flex; justify-content: space-between;
  }}
  .scale-result {{ font-size: 12px; color: var(--danger); font-weight: 600; margin-top: 4px; }}
  /* 量表多次记录 */
  .scale-record-tabs {{ display: flex; gap: 4px; margin-bottom: 8px; flex-wrap: wrap; }}
  .scale-record-tab {{
    padding: 3px 10px; border-radius: 4px; cursor: pointer; font-size: 11px;
    border: 1px solid var(--border); background: white; color: var(--primary);
  }}
  .scale-record-tab.active {{ background: var(--primary); color: white; border-color: var(--primary); }}
  .scale-record-panel {{ display: none; }}
  .scale-record-panel.active {{ display: block; }}
  .scale-history-table {{ margin-top: 10px; font-size: 11px; }}
  .scale-history-table th {{ background: #f0f4f8; }}
  /* 操作记录表 */
  .op-record-table td {{ vertical-align: middle; }}
  /* 会诊行 */
  .consult-row {{ cursor: pointer; }}
  .consult-row:hover td {{ background: #dff0ff; }}
  .consult-row td:first-child {{ color: var(--primary); text-decoration: underline; font-weight: 600; }}
  /* 随访行 */
  .followup-row {{ cursor: pointer; }}
  .followup-row:hover td {{ background: #dff0ff; }}
  .followup-row td:first-child {{ color: var(--primary); text-decoration: underline; font-weight: 600; }}
  /* 不良事件 */
  .adverse-event-btn {{
    display: inline-block; background: #fff0f0; color: var(--danger);
    border: 1px solid #ffcccc; border-radius: 4px; padding: 2px 8px;
    font-size: 11px; cursor: pointer; margin-top: 4px;
  }}
  .adverse-event-btn:hover {{ background: #ffe0e0; }}
  /* 巡查日历 */
  .patrol-tabs {{ display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 10px; }}
  .patrol-tab {{
    padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;
    border: 1px solid var(--border); background: white; color: var(--primary);
  }}
  .patrol-tab.active {{ background: var(--primary); color: white; border-color: var(--primary); }}
  .patrol-day-panel {{ display: none; }}
  .patrol-day-panel.active {{ display: block; }}
  /* 巡查表多选 */
  .multi-check-group {{ display: flex; flex-wrap: wrap; gap: 3px; }}
  .multi-check-item {{
    display: flex; align-items: center; gap: 2px; font-size: 10px;
    padding: 1px 4px; border-radius: 3px; background: #f5f7fa; border: 1px solid #e0e6f0;
    cursor: pointer; user-select: none; white-space: nowrap;
  }}
  .multi-check-item.selected {{ background: var(--primary-light); border-color: var(--primary); color: var(--primary-dark); }}
  .multi-check-item input {{ display: none; }}
  /* 列宽拖拽 */
  .resizable-col {{ position: relative; }}
  .resizer {{
    position: absolute; right: 0; top: 0; bottom: 0; width: 4px; cursor: col-resize;
    background: transparent; z-index: 5;
  }}
  .resizer:hover {{ background: var(--primary); }}
  /* 保存提示 */
  .save-toast {{
    position: fixed; bottom: 20px; right: 20px; background: var(--secondary); color: white;
    padding: 8px 18px; border-radius: 6px; font-size: 13px; z-index: 9999;
    transform: translateY(80px); transition: transform 0.3s;
  }}
  .save-toast.show {{ transform: translateY(0); }}
  /* 打印按钮区域 */
  .edu-print-btns {{ display: flex; gap: 8px; justify-content: flex-end; margin-bottom: 8px; }}
</style>
</head>
<body>

<!-- 保存提示 -->
<div class="save-toast" id="saveToast">✅ 数据已保存</div>

<!-- ===== 页眉 ===== -->
<div class="plan-header">
  <div>
    <h1>🏥 护理监护计划</h1>
    <div class="subtitle">Nursing Monitoring &amp; Care Plan &nbsp;|&nbsp; {department} &nbsp;|&nbsp; 制定日期：{admit_date}</div>
  </div>
  <div class="header-btns no-print">
    <button class="hdr-btn" onclick="saveAllData()">💾 保存数据</button>
    <button class="hdr-btn" onclick="loadAllData()">📂 加载数据</button>
    <button class="hdr-btn" onclick="window.print()">🖨️ 打印计划</button>
  </div>
</div>

<!-- ===== 患者信息 ===== -->
<div class="patient-card" id="patientCard">
  <div style="grid-column:1/-1;display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div style="font-size:14px;font-weight:700;color:var(--primary-dark)">👤 患者基本信息</div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-sm btn-outline" onclick="openPatientEditModal()">✏️ 编辑</button>
      <button class="btn btn-sm btn-outline" onclick="document.getElementById('xlsUpload').click()">📄 上传XLS</button>
      <input type="file" id="xlsUpload" accept=".xls,.xlsx" style="display:none" onchange="handleXLSUpload(event)">
    </div>
  </div>
  <div class="info-item">
    <div class="info-label">患者姓名</div>
    <div class="info-value" id="info_patient_name">{patient_name}</div>
  </div>
  <div class="info-item">
    <div class="info-label">临床诊断</div>
    <div class="info-value" style="color:var(--danger)" id="info_diagnosis">{diagnosis}</div>
  </div>
  <div class="info-item">
    <div class="info-label">护理级别</div>
    <div class="info-value" id="info_nursing_level">{nursing_level}</div>
  </div>
  <div class="info-item">
    <div class="info-label">临床路径周期</div>
    <div class="info-value" id="info_pathway_days">{pathway_days} 天</div>
  </div>
  <div class="info-item">
    <div class="info-label">制定护士</div>
    <div class="info-value" id="info_creator">{creator}</div>
  </div>
  <div class="info-item">
    <div class="info-label">计划日期</div>
    <div class="info-value" id="info_admit_date">{admit_date}</div>
  </div>
  <div class="info-item" id="info_symptoms_item" style="display:{('block' if symptoms else 'none')}">
    <div class="info-label">主要症状</div>
    <div class="info-value" style="font-size:12px;" id="info_symptoms">{symptoms}</div>
  </div>
  <div class="info-item" id="info_medications_item" style="display:{('block' if medications else 'none')}">
    <div class="info-label">用药信息</div>
    <div class="info-value" style="font-size:12px;" id="info_medications">{medications}</div>
  </div>
  <div class="info-item" id="info_examinations_item" style="display:{('block' if examinations else 'none')}">
    <div class="info-label">检查检验</div>
    <div class="info-value" style="font-size:12px;" id="info_examinations">{examinations}</div>
  </div>
  <div class="ref-standards">📋 参考标准：{std_refs_html}</div>
</div>

<div class="content">

<!-- ===== 📅 临床路径护理时间轴（置顶） ===== -->
<div class="section">
  <div class="section-header">
    <span class="section-num" style="border-radius:4px">📅</span> 临床路径护理时间轴（{pathway_days}天）
  </div>
  <div class="section-body">
    <div class="pathway-timeline">
      <table>
        <thead>
          <tr>
            <th style="width:100px">护理项目</th>
            {''.join([f'<th style="min-width:55px;text-align:center">第{r["day"]}天<br><small style="font-weight:400;opacity:0.8">{r["date"]}</small></th>' for r in pathway_rows_data])}
          </tr>
        </thead>
        <tbody>
          {generate_pathway_rows(pathway_rows_data, diagnosis, nursing_level)}
        </tbody>
      </table>
    </div>
    <div style="margin-top:8px;font-size:11px;color:var(--text-light)">
      {''.join([f'<span style="margin-right:12px"><strong>第{r["day"]}天</strong>：{r["focus"]}</span>' for r in pathway_rows_data])}
    </div>
  </div>
</div>

<!-- ===== 一、护理监护医嘱 ===== -->
<div class="section">
  <div class="section-header">
    <span class="section-num">一</span> 护理监护医嘱
  </div>
  <div class="section-body">
    <div class="sub-header">护嘱（{nursing_level}）</div>
    <table>
      <thead>
        <tr><th style="width:36px">序号</th><th>护理医嘱内容</th><th style="width:75px">执行频率</th><th style="width:90px">执行护士</th><th style="width:75px">执行时间</th></tr>
      </thead>
      <tbody>
        {''.join([f'<tr><td style="text-align:center">{i}</td><td>{o}</td><td>按医嘱</td><td><input type="text" placeholder="签名"></td><td><input type="text" placeholder="时间"></td></tr>' for i, o in enumerate(nursing_orders, 1)])}
      </tbody>
    </table>

    <div class="sub-header" style="margin-top:14px">护理操作准备物资</div>
    <table>
      <thead><tr><th style="width:90px">类别</th><th>名称/规格</th><th style="width:55px">数量</th><th style="width:70px">备注</th></tr></thead>
      <tbody>{generate_supplies_rows_v2(supplies)}</tbody>
    </table>
  </div>
</div>

<!-- ===== 二、护理巡查计划 ===== -->
<div class="section">
  <div class="section-header">
    <span class="section-num">二</span> 护理巡查计划
  </div>
  <div class="section-body">
    <div class="sub-header green">巡查频率与项目（{nursing_level}：{patrol_info['frequency']}）</div>
    <table>
      <thead><tr><th>巡查项目</th><th>巡查频率</th><th>观察要点</th><th style="width:90px">异常处理</th></tr></thead>
      <tbody>{generate_patrol_items_rows_v2(patrol_info['items'], patrol_info['frequency'])}</tbody>
    </table>

    <!-- 每日护理巡查登记（多选版） -->
    <div class="sub-header green" style="margin-top:16px">每日护理巡查登记表（多选录入）</div>
    <div class="date-nav no-print">
      <label>登记日期：</label>
      <input type="date" id="patrolDate" value="{now.strftime('%Y-%m-%d')}">
      <button class="btn btn-primary btn-sm" onclick="switchPatrolDay()">切换</button>
      <button class="btn btn-success btn-sm" onclick="savePatrolData()">💾 保存当日记录</button>
      <button class="btn btn-outline btn-sm" onclick="printPatrolSheet()">🖨️ 打印巡查表</button>
      <span class="save-status" id="patrolSaveStatus"></span>
    </div>

    <div class="patrol-tabs no-print" id="patrolTabs">
      {' '.join([f'<span class="patrol-tab{" active" if i==0 else ""}" onclick="showPatrolDay({i})" id="ptab{i}">{(now+timedelta(days=i)).strftime("%m/%d")}</span>' for i in range(min(7, pathway_days))])}
    </div>

    {generate_patrol_day_panels_v3(now, times, patrol_items_display, select_options, pathway_days)}

  </div>
</div>

<!-- ===== 三、护理服务计划 ===== -->

<!-- 3.1 护理评估（含量表多次记录） -->
<div class="section">
  <div class="section-header">
    <span class="section-num">三</span> 护理服务计划
  </div>
  <div class="section-body">
    <div class="sub-header">3.1 护理评估</div>
    {assessment_content}

    <div style="margin-top:12px">
      {generate_all_scales_v3(scale_definitions, pathway_days, now)}
    </div>
  </div>
</div>

<!-- 3.2 护理宣教（可单独打印） -->
<div class="section">
  <div class="section-body">
    <div class="sub-header">3.2 护理宣教</div>
    <div class="edu-print-btns no-print">
      <button class="btn btn-outline btn-sm" onclick="printEducation()">🖨️ 打印宣教内容（给患者）</button>
    </div>
    <div class="edu-grid edu-printable" id="eduPrintable">
      <div class="edu-card admission">
        <div class="edu-card-title">📋 入院宣教</div>
        {generate_education_items_detailed(edu_admission)}
      </div>
      <div class="edu-card inhospital">
        <div class="edu-card-title">🏥 住院期间宣教</div>
        {generate_education_items_detailed(edu_inhospital)}
      </div>
      <div class="edu-card discharge">
        <div class="edu-card-title">🚪 出院前宣教</div>
        {generate_education_items_detailed(edu_discharge)}
      </div>
    </div>
  </div>
</div>

<!-- 3.3 护理操作（含操作要点核查 + 操作记录表） -->
<div class="section">
  <div class="section-body">
    <div class="sub-header">3.3 护理操作（含标准要求）</div>
    {generate_operation_cards_v3(operation_points, diagnosis, pathway_days, now)}
  </div>
</div>

<!-- 3.4 护理监护风险因素清单 -->
<div class="section">
  <div class="section-body">
    <div class="sub-header red">3.4 护理监护风险因素清单</div>
    <div class="risk-grid">
      {generate_risk_cards(risks, pathway_days)}
    </div>
  </div>
</div>

<!-- 3.5 护理会诊 -->
<div class="section">
  <div class="section-body">
    <div class="sub-header">3.5 护理会诊</div>
    <p style="font-size:11px;color:var(--text-light);margin-bottom:8px">💡 点击会诊项目名称，填写并保存完整护理会诊登记单</p>
    <table>
      <thead><tr><th>会诊类型</th><th>会诊目的</th><th style="width:90px">计划时间</th><th style="width:90px">会诊科室</th><th style="width:80px">状态</th></tr></thead>
      <tbody>
        {''.join([f'<tr class="consult-row" onclick="openConsultModal({i})" id="consult-row-{i}"><td>🔍 {c[0]}</td><td>{c[1]}</td><td>{c[2]}</td><td>{c[3]}</td><td><span id="consult-status-{i}" style="font-size:11px;color:var(--text-light)">待填写</span></td></tr>' for i, c in enumerate(consultations)])}
      </tbody>
    </table>
  </div>
</div>

<!-- 3.7 护理随访计划 -->
<div class="section">
  <div class="section-body">
    <div class="sub-header">3.7 护理随访计划</div>
    <p style="font-size:11px;color:var(--text-light);margin-bottom:8px">💡 点击随访时间节点，填写完整随访登记信息</p>
    <table>
      <thead><tr><th style="width:100px">随访时间</th><th style="width:80px">随访方式</th><th>随访内容</th><th style="width:90px">责任护士</th><th style="width:70px">状态</th></tr></thead>
      <tbody>
        {''.join([f'<tr class="followup-row" onclick="openFollowupModal({i})" id="followup-row-{i}"><td>📅 {f[0]}</td><td>{f[1]}</td><td style="font-size:11px">{f[2][:60]}…</td><td><span id="followup-nurse-{i}" style="font-size:11px">待安排</span></td><td><span id="followup-status-{i}" style="font-size:11px;color:var(--text-light)">待随访</span></td></tr>' for i, f in enumerate(followup_list)])}
      </tbody>
    </table>

    <div class="sign-row" style="margin-top:18px">
      <div class="sign-box">责任护士签名：______________</div>
      <div class="sign-box">护士长审核：______________</div>
      <div class="sign-box">主管医生确认：______________</div>
      <div class="sign-box">制表日期：{admit_date}</div>
    </div>
  </div>
</div>

</div><!-- end .content -->

<!-- ===== 模态框区域 ===== -->

<!-- 患者信息编辑模态框 -->
<div class="modal-overlay" id="patientEditModal">
  <div class="modal-box" style="max-width:600px">
    <div class="modal-header">
      <h3>✏️ 编辑患者基本信息</h3>
      <button class="modal-close" onclick="closeModal('patientEditModal')">×</button>
    </div>
    <div class="modal-body">
      <div class="form-row">
        <div class="form-group">
          <label>患者姓名</label>
          <input type="text" id="edit_patient_name" value="{patient_name}">
        </div>
        <div class="form-group">
          <label>临床诊断</label>
          <input type="text" id="edit_diagnosis" value="{diagnosis}">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>护理级别</label>
          <select id="edit_nursing_level">
            <option value="特级护理" {'selected' if nursing_level == '特级护理' else ''}>特级护理</option>
            <option value="一级护理" {'selected' if nursing_level == '一级护理' else ''}>一级护理</option>
            <option value="二级护理" {'selected' if nursing_level == '二级护理' else ''}>二级护理</option>
            <option value="三级护理" {'selected' if nursing_level == '三级护理' else ''}>三级护理</option>
          </select>
        </div>
        <div class="form-group">
          <label>临床路径周期（天）</label>
          <input type="number" id="edit_pathway_days" value="{pathway_days}" min="1" max="30">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>制定护士</label>
          <input type="text" id="edit_creator" value="{creator}">
        </div>
        <div class="form-group">
          <label>计划日期</label>
          <input type="date" id="edit_admit_date" value="{admit_date}">
        </div>
      </div>
      <div class="form-group">
        <label>主要症状</label>
        <textarea id="edit_symptoms" rows="2">{symptoms}</textarea>
      </div>
      <div class="form-group">
        <label>用药信息</label>
        <textarea id="edit_medications" rows="2">{medications}</textarea>
      </div>
      <div class="form-group">
        <label>检查检验</label>
        <textarea id="edit_examinations" rows="2">{examinations}</textarea>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal('patientEditModal')">取消</button>
      <button class="btn btn-primary" onclick="savePatientInfo()">💾 保存</button>
    </div>
  </div>
</div>

<!-- 护理会诊登记模态框 -->
<div class="modal-overlay" id="consultModal">
  <div class="modal-box">
    <div class="modal-header">
      <h3 id="consultModalTitle">护理会诊登记单</h3>
      <button class="modal-close" onclick="closeModal('consultModal')">×</button>
    </div>
    <div class="modal-body">
      <div class="form-row">
        <div class="form-group"><label>申请科室</label><input type="text" id="consult_dept_req" value="{department}"></div>
        <div class="form-group"><label>申请日期</label><input type="date" id="consult_date_req" value="{now.strftime('%Y-%m-%d')}"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>患者姓名</label><input type="text" id="consult_patient" value="{patient_name}"></div>
        <div class="form-group"><label>主要诊断</label><input type="text" id="consult_diagnosis" value="{diagnosis}"></div>
      </div>
      <div class="form-group">
        <label>当前病情摘要（含症状、用药、检查）</label>
        <textarea id="consult_condition" rows="3">{symptoms + (" 用药：" + medications if medications else "") + (" 检查：" + examinations if examinations else "")}</textarea>
      </div>
      <div class="form-group"><label>会诊目的</label><textarea id="consult_purpose" rows="2"></textarea></div>
      <div class="form-group"><label>会诊类型</label><input type="text" id="consult_type" readonly></div>
      <div class="form-row">
        <div class="form-group"><label>会诊科室/专家</label><input type="text" id="consult_expert"></div>
        <div class="form-group"><label>会诊时间</label><input type="datetime-local" id="consult_datetime"></div>
      </div>
      <div class="form-group"><label>会诊意见（结合当前病情）</label><textarea id="consult_opinion" rows="4" placeholder="请填写会诊专家意见..."></textarea></div>
      <div class="form-row">
        <div class="form-group"><label>护理干预措施</label><textarea id="consult_nursing_action" rows="3" placeholder="基于会诊意见的护理干预..."></textarea></div>
        <div class="form-group"><label>随访安排</label><textarea id="consult_followup" rows="3" placeholder="后续随访计划..."></textarea></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>申请护士签名</label><input type="text" id="consult_req_nurse"></div>
        <div class="form-group"><label>会诊护士签名</label><input type="text" id="consult_resp_nurse"></div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal('consultModal')">取消</button>
      <button class="btn btn-success" onclick="saveConsultData()">💾 保存会诊记录</button>
    </div>
  </div>
</div>

<!-- 随访登记模态框 -->
<div class="modal-overlay" id="followupModal">
  <div class="modal-box">
    <div class="modal-header">
      <h3 id="followupModalTitle">护理随访登记表</h3>
      <button class="modal-close" onclick="closeModal('followupModal')">×</button>
    </div>
    <div class="modal-body">
      <div class="form-row">
        <div class="form-group"><label>随访时间</label><input type="text" id="fu_timing" readonly></div>
        <div class="form-group"><label>实际随访日期</label><input type="date" id="fu_date"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>患者姓名</label><input type="text" id="fu_patient" value="{patient_name}"></div>
        <div class="form-group"><label>随访方式</label>
          <select id="fu_method"><option>电话随访</option><option>门诊复诊</option><option>家庭访视</option><option>网络随访</option></select>
        </div>
      </div>
      <div class="form-group"><label>随访内容</label><textarea id="fu_content" rows="3"></textarea></div>
      <div class="form-group"><label>患者现存症状/主诉</label><textarea id="fu_symptoms" rows="2" placeholder="填写患者当前症状或主诉..."></textarea></div>
      <div class="form-row">
        <div class="form-group"><label>用药依从性</label>
          <select id="fu_medication_compliance"><option>规律用药</option><option>偶尔漏服</option><option>频繁漏服</option><option>已自行停药</option></select>
        </div>
        <div class="form-group"><label>居家护理执行情况</label>
          <select id="fu_homecare"><option>完全按照指导执行</option><option>基本按照执行</option><option>部分执行</option><option>未能执行</option></select>
        </div>
      </div>
      <div class="form-group"><label>康复进展评估</label><textarea id="fu_recovery" rows="2" placeholder="描述康复进展情况..."></textarea></div>
      <div class="form-group"><label>护理指导意见（结合当前病情信息）</label><textarea id="fu_guidance" rows="3" placeholder="基于当前病情给出护理建议..."></textarea></div>
      <div class="form-row">
        <div class="form-group"><label>下次随访时间</label><input type="date" id="fu_next_date"></div>
        <div class="form-group"><label>责任护士签名</label><input type="text" id="fu_nurse"></div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal('followupModal')">取消</button>
      <button class="btn btn-success" onclick="saveFollowupData()">💾 保存随访记录</button>
    </div>
  </div>
</div>

<!-- 不良事件登记模态框 -->
<div class="modal-overlay" id="adverseModal">
  <div class="modal-box">
    <div class="modal-header" style="background:var(--danger)">
      <h3>⚠️ 护理不良事件登记表</h3>
      <button class="modal-close" onclick="closeModal('adverseModal')">×</button>
    </div>
    <div class="modal-body">
      <div class="form-row">
        <div class="form-group"><label>发生日期时间</label><input type="datetime-local" id="ae_datetime"></div>
        <div class="form-group"><label>事件类型</label>
          <select id="ae_type"><option>跌倒/坠床</option><option>压力性损伤</option><option>导管脱出</option><option>用药错误</option><option>误吸/窒息</option><option>皮肤损伤</option><option>低血糖</option><option>过敏反应</option><option>气道梗阻</option><option>其他不良事件</option></select>
        </div>
      </div>
      <div class="form-group"><label>事件经过（详细描述）</label><textarea id="ae_description" rows="4" placeholder="请详细描述事件发生的经过..."></textarea></div>
      <div class="form-row">
        <div class="form-group"><label>伤害程度</label>
          <select id="ae_severity"><option>无伤害</option><option>轻度伤害</option><option>中度伤害</option><option>重度伤害</option><option>死亡</option></select>
        </div>
        <div class="form-group"><label>发现者</label><input type="text" id="ae_discoverer" placeholder="发现护士姓名"></div>
      </div>
      <div class="form-group"><label>立即采取的处理措施</label><textarea id="ae_immediate_action" rows="3" placeholder="描述立即采取的应急处理..."></textarea></div>
      <div class="form-group"><label>医生通知时间</label><input type="datetime-local" id="ae_notify_doctor"></div>
      <div class="form-group"><label>护士长通知时间</label><input type="datetime-local" id="ae_notify_head"></div>
      <div class="form-group"><label>后续观察及处理</label><textarea id="ae_followup_action" rows="3" placeholder="后续处理措施及观察结果..."></textarea></div>
      <div class="form-row">
        <div class="form-group"><label>原因分析</label>
          <select id="ae_cause"><option>评估不足</option><option>患者/家属不配合</option><option>护理措施不到位</option><option>设备问题</option><option>环境因素</option><option>其他</option></select>
        </div>
        <div class="form-group"><label>改进措施</label><input type="text" id="ae_improvement" placeholder="填写改进措施"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>报告护士签名</label><input type="text" id="ae_reporter"></div>
        <div class="form-group"><label>护士长审核签名</label><input type="text" id="ae_reviewer"></div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal('adverseModal')">取消</button>
      <button class="btn btn-danger" onclick="saveAdverseData()">⚠️ 提交不良事件报告</button>
    </div>
  </div>
</div>

<script>
// ===== 全局数据存储 Key =====
var STORAGE_KEY = "nursing_care_v3_{patient_name}_{diagnosis}_{now.strftime('%Y%m%d')}".replace(/\\s+/g, '_');
var consultData = {{}};
var followupData = {{}};
var adverseEvents = [];
var currentConsultIdx = -1;
var currentFollowupIdx = -1;
var scaleRecords = {{}}; // 量表多次记录数据

// ===== 不良事件检查函数 =====
function checkAbnormal(el) {{
  var btn = el.nextElementSibling;
  if (el.value && el.value.trim()) {{
    btn.style.display = 'inline-block';
  }} else {{
    btn.style.display = 'none';
  }}
}}

// ===== 风险因素清单行高亮 =====
function toggleRiskRow(cb) {{
  var row = cb.closest("tr");
  if (cb.checked) {{
    row.style.background = "#fff3cd";
  }} else {{
    row.style.background = "";
  }}
}}

// ===== 三测表体温曲线功能 =====
var tprData = {{}}; // 存储三测表数据: {{ day_idx: {{ time: {{t, p, r}} }} }}
function recordTPR(dayIdx, timeStr, field, value) {{
  if (!tprData[dayIdx]) tprData[dayIdx] = {{}};
  if (!tprData[dayIdx][timeStr]) tprData[dayIdx][timeStr] = {{t: '', p: '', r: '', bp: '', spo2: ''}};
  tprData[dayIdx][timeStr][field] = value;
}}
function drawTempCurve() {{
  var canvas = document.getElementById('tempCurveCanvas');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  // 背景网格
  ctx.strokeStyle = '#e0e0e0'; ctx.lineWidth = 1;
  for (var i = 0; i <= 10; i++) {{ ctx.beginPath(); ctx.moveTo(40, 20 + i * (h-40)/10); ctx.lineTo(w-10, 20 + i * (h-40)/10); ctx.stroke(); }}
  for (var i = 0; i <= 14; i++) {{ ctx.beginPath(); ctx.moveTo(40 + i * (w-50)/14, 20); ctx.lineTo(40 + i * (w-50)/14, h-20); ctx.stroke(); }}
  // 标签
  ctx.fillStyle = '#333'; ctx.font = '11px Arial';
  var temps = ['41', '40', '39', '38', '37', '36', '35'];
  for (var i = 0; i < temps.length; i++) {{ ctx.fillText(temps[i] + 'C', 5, 25 + i * (h-40)/6); }}
  // 数据点连线
  var points = [];
  Object.keys(tprData).forEach(function(dayIdx) {{
    Object.keys(tprData[dayIdx]).forEach(function(timeStr) {{
      var t = parseFloat(tprData[dayIdx][timeStr].t);
      if (!isNaN(t) && t >= 35 && t <= 41) {{
        var x = 40 + parseInt(dayIdx) * (w-50)/7 + (parseInt(timeStr.substring(0,2)) / 24) * (w-50)/7;
        var y = 20 + (41 - t) * (h-40)/6;
        points.push({{x: x, y: y, t: t, day: dayIdx, time: timeStr}});
      }}
    }});
  }});
  points.sort(function(a,b) {{ return a.x - b.x; }});
  if (points.length > 1) {{
    ctx.strokeStyle = '#e74c3c'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(points[0].x, points[0].y);
    for (var i = 1; i < points.length; i++) {{ ctx.lineTo(points[i].x, points[i].y); }}
    ctx.stroke();
  }}
  points.forEach(function(p) {{
    ctx.fillStyle = '#e74c3c'; ctx.beginPath(); ctx.arc(p.x, p.y, 3, 0, Math.PI*2); ctx.fill();
    ctx.fillStyle = '#333'; ctx.font = '9px Arial'; ctx.fillText(p.t.toFixed(1), p.x-8, p.y-6);
  }});
}}

// ===== 护理会诊数据 =====
var consultations = {consultations_js};
var followupList = {followup_js};
var pathwayRows = {pathway_rows_js};

// ===== 模态框控制 =====
function openModal(id) {{ document.getElementById(id).classList.add('active'); }}
function closeModal(id) {{ document.getElementById(id).classList.remove('active'); }}
window.addEventListener('click', function(e) {{
  if (e.target.classList.contains('modal-overlay')) e.target.classList.remove('active');
}});

// ===== 会诊模态框 =====
function openConsultModal(idx) {{
  currentConsultIdx = idx;
  var c = consultations[idx];
  document.getElementById('consultModalTitle').textContent = '护理会诊登记单 - ' + c.type;
  document.getElementById('consult_type').value = c.type;
  document.getElementById('consult_purpose').value = c.purpose;
  var saved = consultData[idx] || {{}};
  ['consult_expert','consult_datetime','consult_opinion','consult_nursing_action',
   'consult_followup','consult_req_nurse','consult_resp_nurse'].forEach(function(id) {{
    if (saved[id]) document.getElementById(id).value = saved[id];
  }});
  openModal('consultModal');
}}
function saveConsultData() {{
  var idx = currentConsultIdx;
  consultData[idx] = {{
    consult_expert: document.getElementById('consult_expert').value,
    consult_datetime: document.getElementById('consult_datetime').value,
    consult_opinion: document.getElementById('consult_opinion').value,
    consult_nursing_action: document.getElementById('consult_nursing_action').value,
    consult_followup: document.getElementById('consult_followup').value,
    consult_req_nurse: document.getElementById('consult_req_nurse').value,
    consult_resp_nurse: document.getElementById('consult_resp_nurse').value,
    consult_condition: document.getElementById('consult_condition').value,
    consult_purpose: document.getElementById('consult_purpose').value,
  }};
  var statusEl = document.getElementById('consult-status-' + idx);
  if (statusEl) {{
    statusEl.style.color = 'var(--secondary)';
    statusEl.textContent = '✅ ' + (consultData[idx].consult_datetime ? consultData[idx].consult_datetime.replace('T',' ') : '已填写');
  }}
  saveAllData();
  closeModal('consultModal');
  showToast('会诊记录已保存');
}}

// ===== 随访模态框 =====
function openFollowupModal(idx) {{
  currentFollowupIdx = idx;
  var f = followupList[idx];
  document.getElementById('followupModalTitle').textContent = '护理随访登记表 - ' + f.timing;
  document.getElementById('fu_timing').value = f.timing;
  document.getElementById('fu_content').value = f.content;
  document.getElementById('fu_method').value = f.method || '电话随访';
  var saved = followupData[idx] || {{}};
  ['fu_date','fu_symptoms','fu_medication_compliance','fu_homecare',
   'fu_recovery','fu_guidance','fu_next_date','fu_nurse'].forEach(function(id) {{
    if (saved[id]) {{ var el = document.getElementById(id); if (el) el.value = saved[id]; }}
  }});
  openModal('followupModal');
}}
function saveFollowupData() {{
  var idx = currentFollowupIdx;
  followupData[idx] = {{
    fu_date: document.getElementById('fu_date').value,
    fu_symptoms: document.getElementById('fu_symptoms').value,
    fu_medication_compliance: document.getElementById('fu_medication_compliance').value,
    fu_homecare: document.getElementById('fu_homecare').value,
    fu_recovery: document.getElementById('fu_recovery').value,
    fu_guidance: document.getElementById('fu_guidance').value,
    fu_next_date: document.getElementById('fu_next_date').value,
    fu_nurse: document.getElementById('fu_nurse').value,
  }};
  var nurseEl = document.getElementById('followup-nurse-' + idx);
  var statusEl = document.getElementById('followup-status-' + idx);
  if (nurseEl) nurseEl.textContent = followupData[idx].fu_nurse || '已填写';
  if (statusEl) {{ statusEl.style.color = 'var(--secondary)'; statusEl.textContent = followupData[idx].fu_date ? ('✅ ' + followupData[idx].fu_date) : '✅ 已完成'; }}
  saveAllData();
  closeModal('followupModal');
  showToast('随访记录已保存');
}}

// ===== 不良事件登记 =====
function openAdverseModal(rowId, abnormal) {{
  var now = new Date();
  var dt = now.toISOString().slice(0,16);
  document.getElementById('ae_datetime').value = dt;
  document.getElementById('ae_description').value = abnormal || '';
  openModal('adverseModal');
}}
function saveAdverseData() {{
  var ae = {{
    datetime: document.getElementById('ae_datetime').value,
    type: document.getElementById('ae_type').value,
    description: document.getElementById('ae_description').value,
    severity: document.getElementById('ae_severity').value,
    discoverer: document.getElementById('ae_discoverer').value,
    immediate_action: document.getElementById('ae_immediate_action').value,
    reporter: document.getElementById('ae_reporter').value,
    reviewer: document.getElementById('ae_reviewer').value,
  }};
  adverseEvents.push(ae);
  saveAllData();
  closeModal('adverseModal');
  showToast('⚠️ 不良事件报告已提交并保存');
}}

// ===== 巡查表多日切换 =====
function showPatrolDay(idx) {{
  document.querySelectorAll('.patrol-day-panel').forEach(function(p) {{ p.classList.remove('active'); }});
  document.querySelectorAll('.patrol-tab').forEach(function(t) {{ t.classList.remove('active'); }});
  var panel = document.getElementById('patrol-panel-' + idx);
  var tab = document.getElementById('ptab' + idx);
  if (panel) panel.classList.add('active');
  if (tab) tab.classList.add('active');
}}
function switchPatrolDay() {{
  showToast('请点击上方日期选项卡切换');
}}
function savePatrolData() {{
  saveAllData();
  document.getElementById('patrolSaveStatus').textContent = '✅ 已保存 ' + new Date().toLocaleTimeString();
  showToast('当日巡查记录已保存');
}}

// ===== 宣教打印 =====
function printEducation() {{
  var edu = document.getElementById('eduPrintable');
  if (!edu) return;
  var printWindow = window.open('', '_blank');
  var html = '<html><head><meta charset="UTF-8"><title>护理宣教 - {patient_name}</title>';
  html += '<style>body{{font-family:"Microsoft YaHei",Arial,sans-serif;font-size:12px;color:#2c3e50;padding:20px;}}';
  html += '.edu-card{{margin-bottom:16px;border:1px solid #dce4ef;border-radius:6px;padding:12px;}}';
  html += '.edu-card-title{{font-weight:700;font-size:13px;margin-bottom:8px;padding-bottom:4px;border-bottom:2px solid;}}';
  html += '.admission .edu-card-title{{color:#1a5fa8;border-color:#1a5fa8;}}';
  html += '.inhospital .edu-card-title{{color:#2e8b57;border-color:#2e8b57;}}';
  html += '.discharge .edu-card-title{{color:#e67e22;border-color:#e67e22;}}';
  html += '</style></head><body>';
  html += '<h2 style="color:#1a5fa8">🏥 护理宣教指导单</h2>';
  html += '<p>患者：{patient_name} | 诊断：{diagnosis} | 日期：' + new Date().toLocaleDateString() + '</p><hr>';
  html += edu.innerHTML;
  html += '<hr><p style="font-size:11px;color:#888">责任护士签名：______________  日期：______________</p>';
  html += '</body></html>';
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  setTimeout(function() {{ printWindow.print(); }}, 300);
}}

// ===== 巡查表打印 =====
function printPatrolSheet() {{
  var activePanel = document.querySelector('.patrol-day-panel.active');
  if (!activePanel) {{ showToast('请先选择一个巡查日期'); return; }}
  var printWindow = window.open('', '_blank');
  var html = '<html><head><meta charset="UTF-8"><title>护理巡查登记表 - {patient_name}</title>';
  html += '<style>body{{font-family:\\"Microsoft YaHei\\",Arial,sans-serif;font-size:10px;padding:15px;}}';
  html += 'table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid #999;padding:3px 4px;text-align:left;}}';
  html += 'th{{background:#f0f4f8;font-size:9px;}} td{{font-size:9px;}} .checkbox-col{{font-size:8px;}}';
  html += '</style></head><body>';
  html += '<h3 style="margin:0 0 8px">护理巡查登记表</h3>';
  html += '<p>患者：{patient_name} | 诊断：{diagnosis} | 护理级别：{nursing_level}</p>';
  html += activePanel.innerHTML;
  html += '</body></html>';
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  setTimeout(function() {{ printWindow.print(); }}, 300);
}}

// ===== 量表多次记录系统 =====
var scaleDefs = {json.dumps(scale_definitions, ensure_ascii=False)};

function getScaleRecordId(scaleId, recIdx) {{
  return scaleId + '_rec_' + recIdx;
}}

function addScaleRecord(scaleId) {{
  var def = scaleDefs.find(function(d) {{ return d.id === scaleId; }});
  if (!def) return;
  var records = scaleRecords[scaleId] || [];
  var recIdx = records.length;
  var recId = getScaleRecordId(scaleId, recIdx);
  var recName = prompt('请输入本次评估名称（如：入院评估、术后评估、出院评估）：', '第' + (recIdx + 1) + '次评估');
  if (!recName) recName = '第' + (recIdx + 1) + '次评估';
  records.push({{ name: recName, date: new Date().toISOString().slice(0,10), nurse: '', values: {{}}, conclusion: '' }});
  scaleRecords[scaleId] = records;
  renderScaleRecords(scaleId);
  showToast('已添加新记录：' + recName);
}}

// ===== 量表独立保存功能 =====
function saveScaleData(scaleId) {{
  var def = scaleDefs.find(function(d) {{ return d.id === scaleId; }});
  if (!def) return;
  var records = scaleRecords[scaleId] || [];
  records.forEach(function(rec, idx) {{
    var recId = getScaleRecordId(scaleId, idx);
    var nameEl = document.getElementById(recId + '_name');
    var dateEl = document.getElementById(recId + '_date');
    var nurseEl = document.getElementById(recId + '_nurse');
    var conclusionEl = document.getElementById(recId + '_conclusion');
    if (nameEl) rec.name = nameEl.value;
    if (dateEl) rec.date = dateEl.value;
    if (nurseEl) rec.nurse = nurseEl.value;
    if (conclusionEl) rec.conclusion = conclusionEl.value;
    var values = {{}};
    def.items.forEach(function(item) {{
      var el = document.getElementById(recId + '_' + item.id);
      if (el) values[item.id] = el.value;
    }});
    rec.values = values;
  }});
  scaleRecords[scaleId] = records;
  // 保存到localStorage
  var allData = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
  allData.scales = collectScaleData();
  allData.timestamp = new Date().toLocaleString();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(allData));
  showToast('✅ ' + def.title + ' 已保存（' + records.length + '条记录）');
}}

function renderScaleRecords(scaleId) {{
  var def = scaleDefs.find(function(d) {{ return d.id === scaleId; }});
  if (!def) return;
  var records = scaleRecords[scaleId] || [];
  var container = document.getElementById(scaleId + '_records');
  if (!container) return;

  // Tab头
  var tabsHtml = '<div class="scale-record-tabs">';
  records.forEach(function(rec, idx) {{
    tabsHtml += '<span class="scale-record-tab' + (idx === records.length - 1 ? ' active' : '') + '" onclick="showScaleRecord(\\'' + scaleId + '\\', ' + idx + ')" id="' + scaleId + '_tab_' + idx + '">' + rec.name + '</span>';
  }});
  tabsHtml += '<span class="scale-record-tab" style="background:var(--secondary);color:white;border-color:var(--secondary)" onclick="addScaleRecord(\\'' + scaleId + '\\')">+ 添加记录</span>';
  tabsHtml += '<span class="scale-record-tab" style="background:#27ae60;color:white;border-color:#27ae60;font-size:11px" onclick="saveScaleData(\'' + scaleId + '\')">保存</span>';
  tabsHtml += '</div>';

  // 面板
  var panelsHtml = '';
  records.forEach(function(rec, idx) {{
    var recId = getScaleRecordId(scaleId, idx);
    var isActive = idx === records.length - 1 ? ' active' : '';
    panelsHtml += '<div class="scale-record-panel' + isActive + '" id="' + recId + '_panel">';
    panelsHtml += '<div style="display:flex;gap:8px;margin-bottom:6px;font-size:11px">';
    panelsHtml += '<label>评估名称：<input type="text" id="' + recId + '_name" value="' + (rec.name || '') + '" style="width:120px" onchange="updateScaleRecordName(\\'' + scaleId + '\\', ' + idx + ')"></label>';
    panelsHtml += '<label>评估日期：<input type="date" id="' + recId + '_date" value="' + (rec.date || '') + '"></label>';
    panelsHtml += '<label>评估护士：<input type="text" id="' + recId + '_nurse" value="' + (rec.nurse || '') + '" style="width:80px"></label>';
    panelsHtml += '</div>';

    // 量表项目
    def.items.forEach(function(item, iidx) {{
      var itemRecId = recId + '_' + item.id;
      var savedVal = rec.values[item.id] || '';
      panelsHtml += '<div class="scale-item">';
      panelsHtml += '<span class="scale-item-label">' + item.label + '</span>';
      panelsHtml += '<span class="scale-item-score"><select id="' + itemRecId + '" onchange="calcScaleRecord(\\'' + scaleId + '\\', ' + idx + ')">';
      panelsHtml += '<option value="">--</option>';
      item.options.forEach(function(opt) {{
        panelsHtml += '<option value="' + opt.value + '"' + (savedVal == opt.value ? ' selected' : '') + '>' + opt.label + '</option>';
      }});
      panelsHtml += '</select></span></div>';
    }});

    // 总分和结果
    panelsHtml += '<div class="scale-total"><span id="' + recId + '_total">总分：0</span>';
    panelsHtml += '<button class="btn btn-primary btn-sm" onclick="calcScaleRecord(\\'' + scaleId + '\\', ' + idx + ')">计算</button></div>';
    panelsHtml += '<div class="scale-result" id="' + recId + '_result"></div>';
    panelsHtml += '<div style="margin-top:6px"><label style="font-size:11px">评估结论/护理措施：</label><textarea id="' + recId + '_conclusion" rows="2" style="width:100%;font-size:11px" placeholder="填写评估结论及护理措施...">' + (rec.conclusion || '') + '</textarea></div>';
    panelsHtml += '</div>';
  }});

  container.innerHTML = tabsHtml + panelsHtml;

  // 自动计算最新记录
  if (records.length > 0) {{
    calcScaleRecord(scaleId, records.length - 1);
  }}
}}

function showScaleRecord(scaleId, idx) {{
  var records = scaleRecords[scaleId] || [];
  records.forEach(function(_, i) {{
    var tab = document.getElementById(scaleId + '_tab_' + i);
    var panel = document.getElementById(getScaleRecordId(scaleId, i) + '_panel');
    if (tab) tab.classList.toggle('active', i === idx);
    if (panel) panel.classList.toggle('active', i === idx);
  }});
}}

function updateScaleRecordName(scaleId, idx) {{
  var records = scaleRecords[scaleId] || [];
  var el = document.getElementById(getScaleRecordId(scaleId, idx) + '_name');
  if (el && records[idx]) {{
    records[idx].name = el.value;
    var tab = document.getElementById(scaleId + '_tab_' + idx);
    if (tab) tab.textContent = el.value;
  }}
}}

function calcScaleRecord(scaleId, recIdx) {{
  var def = scaleDefs.find(function(d) {{ return d.id === scaleId; }});
  if (!def) return;
  var recId = getScaleRecordId(scaleId, recIdx);
  var total = 0;
  def.items.forEach(function(item) {{
    var el = document.getElementById(recId + '_' + item.id);
    if (el) total += parseInt(el.value) || 0;
  }});
  var totalEl = document.getElementById(recId + '_total');
  var resultEl = document.getElementById(recId + '_result');
  if (totalEl) totalEl.textContent = '总分：' + total;
  if (resultEl && def.thresholds) {{
    var result = '';
    for (var i = 0; i < def.thresholds.length; i++) {{
      if (total <= def.thresholds[i].score) {{ result = def.thresholds[i].label; break; }}
    }}
    resultEl.textContent = result;
    resultEl.style.color = (result.indexOf('高') >= 0 || result.indexOf('重度') >= 0 || result.indexOf('严重') >= 0) ? 'var(--danger)' : 'var(--secondary)';
  }}
}}

function collectScaleData() {{
  var data = {{}};
  scaleDefs.forEach(function(def) {{
    var scaleId = def.id;
    var records = scaleRecords[scaleId] || [];
    data[scaleId] = records.map(function(rec, idx) {{
      var recId = getScaleRecordId(scaleId, idx);
      var values = {{}};
      def.items.forEach(function(item) {{
        var el = document.getElementById(recId + '_' + item.id);
        if (el) values[item.id] = el.value;
      }});
      var nameEl = document.getElementById(recId + '_name');
      var dateEl = document.getElementById(recId + '_date');
      var nurseEl = document.getElementById(recId + '_nurse');
      var conclusionEl = document.getElementById(recId + '_conclusion');
      return {{
        name: nameEl ? nameEl.value : rec.name,
        date: dateEl ? dateEl.value : rec.date,
        nurse: nurseEl ? nurseEl.value : rec.nurse,
        values: values,
        conclusion: conclusionEl ? conclusionEl.value : rec.conclusion
      }};
    }});
  }});
  return data;
}}

function restoreScaleData(data) {{
  if (!data) return;
  scaleDefs.forEach(function(def) {{
    var scaleId = def.id;
    if (data[scaleId]) {{
      scaleRecords[scaleId] = data[scaleId];
      renderScaleRecords(scaleId);
    }}
  }});
}}

function toggleScale(id) {{
  var body = document.getElementById(id + '_body');
  if (body) body.classList.toggle('open');
}}

// ===== 多选框逻辑 =====
function toggleMultiCheck(el) {{
  el.classList.toggle('selected');
  var hidden = el.querySelector('input[type=hidden]');
  if (hidden) {{
    var selected = [];
    var group = el.closest('.multi-check-group');
    if (group) {{
      group.querySelectorAll('.multi-check-item.selected').forEach(function(s) {{
        var txt = s.textContent.trim();
        if (txt) selected.push(txt);
      }});
    }}
    hidden.value = selected.join('、');
  }}
}}

// ===== 核查checkbox =====
document.querySelectorAll('.checklist-item input[type=checkbox]').forEach(function(cb) {{
  cb.addEventListener('change', function() {{
    this.closest('.checklist-item').style.opacity = this.checked ? '0.5' : '1';
    this.closest('.checklist-item').querySelector('label').style.textDecoration = this.checked ? 'line-through' : 'none';
  }});
}});

// ===== 列宽拖拽 =====
function initColumnResize(tableId) {{
  var table = document.getElementById(tableId);
  if (!table) return;
  var cols = table.querySelectorAll('th');
  cols.forEach(function(th) {{
    th.classList.add('resizable-col');
    var resizer = document.createElement('div');
    resizer.className = 'resizer';
    th.appendChild(resizer);
    var startX, startWidth;
    resizer.addEventListener('mousedown', function(e) {{
      startX = e.pageX;
      startWidth = th.offsetWidth;
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    }});
    function onMouseMove(e) {{
      var newWidth = startWidth + (e.pageX - startX);
      if (newWidth > 40) th.style.width = newWidth + 'px';
    }}
    function onMouseUp() {{
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    }}
  }});
}}

// ===== 全局保存/加载 =====
function collectAllData() {{
  var data = {{
    consultData: consultData,
    followupData: followupData,
    adverseEvents: adverseEvents,
    patrolPanels: {{}},
    detailPatrol: {{}},
    scales: collectScaleData(),
    timestamp: new Date().toISOString()
  }};
  document.querySelectorAll('.patrol-day-panel').forEach(function(panel) {{
    var pid = panel.id;
    var vals = {{}};
    panel.querySelectorAll('select,input,textarea,.multi-check-group input[type=hidden]').forEach(function(el) {{
      if (el.id) vals[el.id] = el.value;
    }});
    data.patrolPanels[pid] = vals;
  }});
  document.querySelectorAll('#detailPatrolTable select, #detailPatrolTable input, #detailPatrolTable textarea').forEach(function(el) {{
    if (el.id) data.detailPatrol[el.id] = el.value;
  }});
  return data;
}}

// 操作记录相关函数
var operationRecordCounters = {{}};

function addOperationRecord(opIdx) {{
  if (!operationRecordCounters[opIdx]) {{
    operationRecordCounters[opIdx] = 8;
  }}
  
  var tbody = document.getElementById('op-record-tbody-' + opIdx);
  if (!tbody) {{
    console.error('找不到操作记录表格:', opIdx);
    return;
  }}
  
  var rowIdx = operationRecordCounters[opIdx];
  var rowId = 'opr' + opIdx + '_' + rowIdx;
  
  var today = new Date();
  var recDate = new Date(today);
  recDate.setDate(today.getDate() + (rowIdx % 7));
  var recDateStr = recDate.toISOString().split('T')[0];
  
  var newRow = document.createElement('tr');
  newRow.id = 'op-record-row-' + opIdx + '-' + rowIdx;
  newRow.innerHTML = '<td style="text-align:center">' + (rowIdx + 1) + '</td>'
    + '<td style="font-size:11px"><input type="text" id="' + rowId + '_item" placeholder="请输入操作项目" style="width:100%;border:1px solid #ddd;padding:2px;font-size:11px"></td>'
    + '<td><input type="text" id="' + rowId + '_operator" placeholder="签名"></td>'
    + '<td><input type="date" id="' + rowId + '_rec_date" value="' + recDateStr + '"></td>'
    + '<td><input type="datetime-local" id="' + rowId + '_actual_time"></td>'
    + '<td><select id="' + rowId + '_result"><option value="">--</option><option>完成</option><option>未完成</option><option>跳过</option></select></td>'
    + '<td><input type="text" id="' + rowId + '_note" placeholder="备注" style="width:100%"></td>'
    + '<td style="text-align:center"><button class="btn btn-danger" style="font-size:10px;padding:2px 6px" onclick="deleteOperationRecord(' + opIdx + ',' + rowIdx + ')">🗑️</button></td>';
  
  tbody.appendChild(newRow);
  operationRecordCounters[opIdx]++;
  showToast('已添加操作记录行');
}}

function deleteOperationRecord(opIdx, rowIdx) {{
  var row = document.getElementById('op-record-row-' + opIdx + '-' + rowIdx);
  if (row) {{
    row.remove();
    showToast('已删除操作记录行');
  }}
}}
function saveAllData() {{
  try {{
    var data = collectAllData();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    showToast('数据已保存到本地');
  }} catch(e) {{ console.error('保存失败', e); }}
}}
function loadAllData() {{
  try {{
    var raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {{ showToast('未找到已保存数据'); return; }}
    var data = JSON.parse(raw);
    consultData = data.consultData || {{}};
    followupData = data.followupData || {{}};
    adverseEvents = data.adverseEvents || [];
    Object.keys(consultData).forEach(function(idx) {{
      var statusEl = document.getElementById('consult-status-' + idx);
      if (statusEl && consultData[idx].consult_datetime) {{
        statusEl.style.color = 'var(--secondary)'; statusEl.textContent = '✅ 已填写';
      }}
    }});
    Object.keys(followupData).forEach(function(idx) {{
      var nurseEl = document.getElementById('followup-nurse-' + idx);
      var statusEl = document.getElementById('followup-status-' + idx);
      if (nurseEl) nurseEl.textContent = followupData[idx].fu_nurse || '已填写';
      if (statusEl) {{ statusEl.style.color = 'var(--secondary)'; statusEl.textContent = '✅ 已完成'; }}
    }});
    if (data.patrolPanels) {{
      Object.keys(data.patrolPanels).forEach(function(pid) {{
        var panel = document.getElementById(pid);
        if (panel) {{
          Object.keys(data.patrolPanels[pid]).forEach(function(eid) {{
            var el = document.getElementById(eid);
            if (el) el.value = data.patrolPanels[pid][eid];
          }});
        }}
      }});
    }}
    if (data.detailPatrol) {{
      Object.keys(data.detailPatrol).forEach(function(eid) {{
        var el = document.getElementById(eid);
        if (el) el.value = data.detailPatrol[eid];
      }});
    }}
    if (data.scales) {{
      scaleRecords = data.scales;
      scaleDefs.forEach(function(def) {{
        if (scaleRecords[def.id] && scaleRecords[def.id].length > 0) {{
          renderScaleRecords(def.id);
        }}
      }});
    }}
    showToast('✅ 数据加载成功 (' + (data.timestamp || '') + ')');
  }} catch(e) {{ showToast('加载失败：' + e.message); }}
}}

function showToast(msg) {{
  var t = document.getElementById('saveToast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function() {{ t.classList.remove('show'); }}, 2500);
}}

// 页面加载时初始化
window.addEventListener('DOMContentLoaded', function() {{
  loadAllData();
  initColumnResize('detailPatrolTable');
  // 初始化量表默认记录
  scaleDefs.forEach(function(def) {{
    if (!scaleRecords[def.id] || scaleRecords[def.id].length === 0) {{
      scaleRecords[def.id] = [{{ name: '入院评估', date: new Date().toISOString().slice(0,10), nurse: '', values: {{}}, conclusion: '' }}];
      renderScaleRecords(def.id);
    }}
  }});
}});

// ===== 患者信息编辑功能 =====
function openPatientEditModal() {{
  document.getElementById('patientEditModal').classList.add('active');
}}

function savePatientInfo() {{
  // 获取编辑框中的值
  var patientName = document.getElementById('edit_patient_name').value;
  var diagnosis = document.getElementById('edit_diagnosis').value;
  var nursingLevel = document.getElementById('edit_nursing_level').value;
  var pathwayDays = document.getElementById('edit_pathway_days').value;
  var creator = document.getElementById('edit_creator').value;
  var admitDate = document.getElementById('edit_admit_date').value;
  var symptoms = document.getElementById('edit_symptoms').value;
  var medications = document.getElementById('edit_medications').value;
  var examinations = document.getElementById('edit_examinations').value;
  
  // 更新页面显示
  document.getElementById('info_patient_name').textContent = patientName;
  document.getElementById('info_diagnosis').textContent = diagnosis;
  document.getElementById('info_nursing_level').textContent = nursingLevel;
  document.getElementById('info_pathway_days').textContent = pathwayDays + ' 天';
  document.getElementById('info_creator').textContent = creator;
  document.getElementById('info_admit_date').textContent = admitDate;
  
  // 更新主要症状（显示/隐藏）
  var symptomsItem = document.getElementById('info_symptoms_item');
  var symptomsEl = document.getElementById('info_symptoms');
  if (symptoms) {{
    symptomsItem.style.display = 'block';
    symptomsEl.textContent = symptoms;
  }} else {{
    symptomsItem.style.display = 'none';
  }}
  
  // 更新用药信息
  var medicationsItem = document.getElementById('info_medications_item');
  var medicationsEl = document.getElementById('info_medications');
  if (medications) {{
    medicationsItem.style.display = 'block';
    medicationsEl.textContent = medications;
  }} else {{
    medicationsItem.style.display = 'none';
  }}
  
  // 更新检查检验
  var examinationsItem = document.getElementById('info_examinations_item');
  var examinationsEl = document.getElementById('info_examinations');
  if (examinations) {{
    examinationsItem.style.display = 'block';
    examinationsEl.textContent = examinations;
  }} else {{
    examinationsItem.style.display = 'none';
  }}
  
  // 关闭模态框
  closeModal('patientEditModal');
  
  // 显示保存提示
  showSaveToast('患者信息已更新');
  
  // 保存到localStorage
  saveAllData();
}}

function closeModal(modalId) {{
  var modal = document.getElementById(modalId);
  if (modal) {{
    modal.classList.remove('active');
  }}
}}

function showSaveToast(msg) {{
  var toast = document.getElementById('saveToast');
  if (toast) {{
    toast.textContent = '✅ ' + (msg || '数据已保存');
    toast.classList.add('show');
    setTimeout(function() {{
      toast.classList.remove('show');
    }}, 2000);
  }}
}}

// ===== XLS文件上传功能 =====
function handleXLSUpload(event) {{
  var file = event.target.files[0];
  if (!file) return;
  
  var fileName = file.name.toLowerCase();
  
  // 检查文件类型
  if (!fileName.endsWith('.xls') && !fileName.endsWith('.xlsx') && !fileName.endsWith('.csv')) {{
    alert('请上传.xls、.xlsx或.csv格式的文件');
    return;
  }}
  
  // 如果是CSV文件，直接解析
  if (fileName.endsWith('.csv')) {{
    parseCSV(file);
    return;
  }}
  
  // 如果是XLS/XLSX文件，需要SheetJS库支持
  // 检查是否已加载SheetJS
  if (typeof XLSX === 'undefined') {{
    // 提示用户需要加载SheetJS库
    var useCSV = confirm('XLS/XLSX文件解析需要SheetJS库支持。\\n\\n是否将文件另存为CSV格式后重新上传？\\n\\n点击"确定"继续（将尝试简单解析），点击"取消"取消上传。');
    if (!useCSV) {{
      event.target.value = '';
      return;
    }}
  }}
  
  // 尝试解析（如果SheetJS已加载）
  if (typeof XLSX !== 'undefined') {{
    parseXLSX(file);
  }} else {{
    // 简单解析（仅文本）
    parseXLSText(file);
  }}
}}

function parseCSV(file) {{
  var reader = new FileReader();
  reader.onload = function(e) {{
    try {{
      var text = e.target.result;
      var lines = text.split('\\n');
      if (lines.length < 2) {{
        alert('CSV文件内容为空或格式不正确');
        return;
      }}
      
      // 假设第一行是标题行
      var headers = lines[0].split(',').map(function(h) {{ return h.trim(); }});
      
      // 查找关键字段的索引
      var nameIdx = findIndex(headers, ['患者姓名', '姓名', '名字', 'name']);
      var diagIdx = findIndex(headers, ['诊断', '临床诊断', 'diagnosis', '疾病']);
      var levelIdx = findIndex(headers, ['护理级别', '级别', 'nursing level']);
      var daysIdx = findIndex(headers, ['路径周期', '天数', 'days', '住院天数']);
      var creatorIdx = findIndex(headers, ['制定护士', '护士', 'creator', '责任护士']);
      var dateIdx = findIndex(headers, ['日期', '计划日期', 'date', '入院日期']);
      var symptomsIdx = findIndex(headers, ['症状', '主要症状', 'symptoms']);
      var medIdx = findIndex(headers, ['用药', '药物', 'medications', '药品']);
      var examIdx = findIndex(headers, ['检查', '检验', 'examinations']);
      
      // 使用第二行数据（第一行是标题）
      var data = lines[1].split(',');
      
      // 填充编辑框
      if (nameIdx >= 0 && data[nameIdx]) document.getElementById('edit_patient_name').value = data[nameIdx].trim();
      if (diagIdx >= 0 && data[diagIdx]) document.getElementById('edit_diagnosis').value = data[diagIdx].trim();
      if (levelIdx >= 0 && data[levelIdx]) document.getElementById('edit_nursing_level').value = data[levelIdx].trim();
      if (daysIdx >= 0 && data[daysIdx]) document.getElementById('edit_pathway_days').value = data[daysIdx].trim();
      if (creatorIdx >= 0 && data[creatorIdx]) document.getElementById('edit_creator').value = data[creatorIdx].trim();
      if (dateIdx >= 0 && data[dateIdx]) document.getElementById('edit_admit_date').value = data[dateIdx].trim();
      if (symptomsIdx >= 0 && data[symptomsIdx]) document.getElementById('edit_symptoms').value = data[symptomsIdx].trim();
      if (medIdx >= 0 && data[medIdx]) document.getElementById('edit_medications').value = data[medIdx].trim();
      if (examIdx >= 0 && data[examIdx]) document.getElementById('edit_examinations').value = data[examIdx].trim();
      
      alert('CSV文件解析完成！请检查并确认信息无误后点击"保存"。');
      openPatientEditModal();
    }} catch (err) {{
      alert('CSV文件解析失败：' + err.message);
    }}
  }};
  reader.readAsText(file, 'UTF-8');
}}

function findIndex(arr, possibleNames) {{
  for (var i = 0; i < possibleNames.length; i++) {{
    var idx = arr.findIndex(function(h) {{
      return h.toLowerCase().includes(possibleNames[i].toLowerCase());
    }});
    if (idx >= 0) return idx;
  }}
  return -1;
}}

function parseXLSX(file) {{
  // 使用SheetJS库解析XLSX文件
  var reader = new FileReader();
  reader.onload = function(e) {{
    try {{
      var data = new Uint8Array(e.target.result);
      var workbook = XLSX.read(data, {{ type: 'array' }});
      var firstSheet = workbook.Sheets[workbook.SheetNames[0]];
      var jsonData = XLSX.utils.sheet_to_json(firstSheet, {{ header: 1 }});
      
      if (jsonData.length < 2) {{
        alert('XLS文件内容为空或格式不正确');
        return;
      }}
      
      // 处理解析后的数据（类似CSV解析）
      alert('XLS文件解析完成！功能开发中...');
    }} catch (err) {{
      alert('XLS文件解析失败：' + err.message);
    }}
  }};
  reader.readAsArrayBuffer(file);
}}

function parseXLSText(file) {{
  // 简单解析：尝试作为文本读取
  var reader = new FileReader();
  reader.onload = function(e) {{
    try {{
      var text = e.target.result;
      // 尝试按行分割
      var lines = text.split('\\n');
      alert('文件已读取，但格式可能无法正确解析。\\n\\n建议将文件另存为CSV格式后重新上传。\\n\\n文件内容预览：\\n' + lines.slice(0, 5).join('\\n'));
    }} catch (err) {{
      alert('文件读取失败：' + err.message);
    }}
  }};
  reader.readAsText(file, 'UTF-8');
}}

</script>

</body>
</html>"""

    return html


# ===== 辅助HTML生成函数 v3 =====

def generate_supplies_rows_v2(supplies):
    rows = ""
    for category, items in supplies.items():
        if items:
            first = True
            valid_items = [i for i in items if i]
            rowspan = len(valid_items)
            for item in valid_items:
                item_text = item if len(item) < 100 else item[:100] + "..."
                cat_cell = f'<td rowspan="{rowspan}" style="font-weight:600;background:#f8f9fa;vertical-align:middle">{category}</td>' if first else ""
                rows += f'<tr>{cat_cell}<td>{item_text}</td><td><input type="text" value="适量" style="width:50px"></td><td><input type="text"></td></tr>'
                first = False
    if not rows:
        rows = '<tr><td>通用护理耗材</td><td>无菌手套、棉签、纱布、胶布等</td><td>按需</td><td></td></tr>'
    return rows


def generate_patrol_items_rows_v2(items, frequency):
    obs_points = {
        "意识状态": "清醒/嗜睡/昏迷；GCS评分",
        "生命体征（至少每4小时）": "T36-37.2℃，P60-100次/分，R12-20次/分，BP90-140/60-90mmHg",
        "皮肤受压情况": "颜色/温度/湿度/完整性；骨突处受压情况",
        "管道固定与通畅": "管道标签/固定/通畅/接口连接/引流量",
        "静脉输液情况": "滴速/渗出/肿胀/发红",
        "排泄情况": "尿量（>0.5ml/kg/h）/大便性状",
        "瞳孔变化": "等大等圆/对光反射",
        "安全防护": "床档/约束/呼叫铃",
    }
    # 异常处理的智能默认值
    abnormal_handling_defaults = {
        "意识状态": "意识障碍立即通知医生，评估GCS评分",
        "生命体征（至少每4小时）": "生命体征异常立即复测，通知医生",
        "皮肤受压情况": "发现压疮立即通知医生，执行压疮护理",
        "管道固定与通畅": "管道脱出/堵塞立即通知医生，停止输液/引流",
        "静脉输液情况": "输液外渗立即停止输液，通知医生",
        "排泄情况": "少尿/无尿立即通知医生，记录24小时出入量",
        "瞳孔变化": "瞳孔异常扩大/缩小或对光反射消失立即通知医生",
        "安全防护": "发生跌倒/坠床立即评估伤情，通知医生",
    }
    rows = ""
    for item in items:
        obs = obs_points.get(item, "观察有无异常变化，与基线比较")
        abnormal_default = abnormal_handling_defaults.get(item, "立即汇报医生，执行应急处理")
        item_id = item.replace("（", "_").replace("）", "_").replace("/", "_").replace(" ", "_")[:20]
        rows += f'<tr><td>{item}</td><td>{frequency}</td><td style="font-size:11px">{obs}</td>'
        rows += f'<td><input type="text" id="abnormal_{item_id}" value="{abnormal_default}" style="width:100%;min-width:120px;font-size:11px" onchange="saveAbnormalHandling()"></td></tr>'
    return rows


def generate_patrol_day_panels_v3(now, times, items, select_options, pathway_days):
    """生成多日巡查面板（合并巡查表+三测表+体温折线图）"""
    consciousness_opts = ["清醒", "嗜睡", "昏睡", "浅昏迷", "深昏迷"]
    skin_opts = ["完整无异常", "局部潮红", "破损/压疮", "水肿/皮疹"]
    tube_opts = ["固定通畅", "固定松动", "引流不畅", "脱出/移位"]
    excrete_opts = ["正常", "少尿/无尿", "腹泻", "便秘", "失禁"]
    
    html = ""
    # 三测表JS函数已移至页面底部主script块中
    
    for day_idx in range(min(7, pathway_days)):
        date = now + timedelta(days=day_idx)
        date_str = date.strftime("%Y-%m-%d")
        active = " active" if day_idx == 0 else ""
        html += f'<div class="patrol-day-panel{active}" id="patrol-panel-{day_idx}">'
        html += f'<p style="font-size:12px;color:#1a5fa8;font-weight:700;margin-bottom:8px">📅 {date.strftime("%Y年%m月%d日")} 护理巡查登记</p>'
        
        # 合并巡查表：时间+意识+生命体征(T/P/R/BP/SpO2)+皮肤+管道+排泄+异常+签名
        html += '<div style="overflow-x:auto"><table class="patrol-printable" id="patrol-table-' + str(day_idx) + '"><thead><tr>'
        html += '<th style="width:50px">时间</th>'
        html += '<th style="width:70px">意识状态</th>'
        html += '<th style="width:55px">体温<br><small>(C)</small></th>'
        html += '<th style="width:55px">脉搏<br><small>(次/分)</small></th>'
        html += '<th style="width:55px">呼吸<br><small>(次/分)</small></th>'
        html += '<th style="width:80px">血压<br><small>(mmHg)</small></th>'
        html += '<th style="width:55px">SpO2<br><small>(%)</small></th>'
        html += '<th style="width:75px">皮肤情况</th>'
        html += '<th style="width:75px">管道情况</th>'
        html += '<th style="width:70px">排泄情况</th>'
        html += '<th>异常情况/处理<br><small>（填写后可报不良事件）</small></th>'
        html += '<th style="width:50px">签名</th>'
        html += '</tr></thead><tbody>'
        
        for time_str in times[:12]:
            row_id = f"pr_{day_idx}_{time_str.replace(':','')}"
            tpr_key = time_str.replace(':', '')
            html += f'<tr><td class="time-col">{time_str}</td>'
            # 意识状态
            html += f'<td><select id="{row_id}_consciousness" style="font-size:11px">'
            html += '<option value="">--</option>' + ''.join([f'<option>{o}</option>' for o in consciousness_opts]) + '</select></td>'
            # 生命体征 T/P/R/BP/SpO2
            html += f'<td><input type="text" id="{row_id}_t" style="width:50px;font-size:11px" placeholder="36.5" onchange="recordTPR({day_idx}, \'{time_str}\', \'t\', this.value); drawTempCurve();"></td>'
            html += f'<td><input type="text" id="{row_id}_p" style="width:50px;font-size:11px" placeholder="80" onchange="recordTPR({day_idx}, \'{time_str}\', \'p\', this.value)"></td>'
            html += f'<td><input type="text" id="{row_id}_r" style="width:50px;font-size:11px" placeholder="18" onchange="recordTPR({day_idx}, \'{time_str}\', \'r\', this.value)"></td>'
            html += f'<td><input type="text" id="{row_id}_bp" style="width:75px;font-size:11px" placeholder="120/80" onchange="recordTPR({day_idx}, \'{time_str}\', \'bp\', this.value)"></td>'
            html += f'<td><input type="text" id="{row_id}_spo2" style="width:50px;font-size:11px" placeholder="98" onchange="recordTPR({day_idx}, \'{time_str}\', \'spo2\', this.value)"></td>'
            # 皮肤
            html += f'<td><select id="{row_id}_skin" style="font-size:11px">'
            html += '<option value="">--</option>' + ''.join([f'<option>{o}</option>' for o in skin_opts]) + '</select></td>'
            # 管道
            html += f'<td><select id="{row_id}_tube" style="font-size:11px">'
            html += '<option value="">--</option>' + ''.join([f'<option>{o}</option>' for o in tube_opts]) + '</select></td>'
            # 排泄
            html += f'<td><select id="{row_id}_excrete" style="font-size:11px">'
            html += '<option value="">--</option>' + ''.join([f'<option>{o}</option>' for o in excrete_opts]) + '</select></td>'
            # 异常+不良事件
            abnormal_id = f"{row_id}_abnormal"
            html += f'<td><input type="text" id="{abnormal_id}" placeholder="异常描述/处理措施" style="width:120px;font-size:11px" onchange="checkAbnormal(this)">'
            html += f'<span class="adverse-event-btn no-print" onclick="openAdverseModal(\'{row_id}\', document.getElementById(\'{abnormal_id}\').value)">⚠️</span></td>'
            html += f'<td><input type="text" id="{row_id}_sign" placeholder="签名" style="width:48px;font-size:11px"></td>'
            html += '</tr>'
        
        html += '</tbody></table></div>'
        
        # 三测表汇总（当日T/P/R汇总表）
        html += f'<div style="margin-top:12px;padding:10px;background:#f8fafc;border-radius:6px;border:1px solid #dce4ef">'
        html += f'<div style="font-weight:700;font-size:12px;color:#0d3d7a;margin-bottom:6px">📊 当日三测表汇总 ({date.strftime("%m月%d日")})</div>'
        html += '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        html += '<thead><tr style="background:#e8f0fa"><th style="border:1px solid #ccc;padding:4px">时间</th>'
        for t in times[:6]:
            html += f'<th style="border:1px solid #ccc;padding:4px;text-align:center">{t}</th>'
        html += '</tr></thead><tbody>'
        for metric, label, unit in [('t', '体温', 'C'), ('p', '脉搏', '次/分'), ('r', '呼吸', '次/分')]:
            html += f'<tr><td style="border:1px solid #ccc;padding:4px;font-weight:600">{label} ({unit})</td>'
            for t in times[:6]:
                tid = t.replace(':','')
                html += f'<td style="border:1px solid #ccc;padding:4px;text-align:center"><span id="tpr_{day_idx}_{tid}_{metric}" style="color:#888">--</span></td>'
            html += '</tr>'
        html += '</tbody></table>'
        html += '</div>'
        
        html += '</div>'
    
    # 体温折线图（Canvas）
    html += '<div style="margin-top:16px;padding:12px;background:#fff;border-radius:8px;border:1px solid #dce4ef">'
    html += '<div style="font-weight:700;font-size:13px;color:#0d3d7a;margin-bottom:8px">🌡️ 体温变化曲线（三测表折线图）</div>'
    html += '<canvas id="tempCurveCanvas" width="700" height="200" style="border:1px solid #ddd;border-radius:4px"></canvas>'
    html += '<div style="font-size:11px;color:#888;margin-top:4px">💡 在巡查表中输入体温数据后，自动绘制体温变化曲线</div>'
    html += '</div>'
    return html


def generate_detail_patrol_rows_v3(now, pathway_days):
    """3.6护理巡查记录表已合并到每日巡查表中，此函数保留兼容但返回空"""
    return ""


def get_scale_definitions():
    """返回量表定义（含完整项目，按指南标准）"""
    return [
        {
            "id": "braden",
            "title": "Braden量表（压力性损伤风险）",
            "items": [
                {"id": "sensory", "label": "感知能力（对压力相关不适的反应）",
                 "options": [{"label": "1-完全受限", "value": 1}, {"label": "2-非常受限", "value": 2}, {"label": "3-轻度受限", "value": 3}, {"label": "4-未受损", "value": 4}]},
                {"id": "moisture", "label": "潮湿程度（皮肤暴露于潮湿的程度）",
                 "options": [{"label": "1-持续潮湿", "value": 1}, {"label": "2-非常潮湿", "value": 2}, {"label": "3-偶尔潮湿", "value": 3}, {"label": "4-很少潮湿", "value": 4}]},
                {"id": "activity", "label": "活动能力（身体活动的程度）",
                 "options": [{"label": "1-卧床", "value": 1}, {"label": "2-坐椅", "value": 2}, {"label": "3-偶尔步行", "value": 3}, {"label": "4-经常步行", "value": 4}]},
                {"id": "mobility", "label": "移动能力（改变和控制体位的能力）",
                 "options": [{"label": "1-完全受限", "value": 1}, {"label": "2-非常受限", "value": 2}, {"label": "3-轻度受限", "value": 3}, {"label": "4-未受限", "value": 4}]},
                {"id": "nutrition", "label": "营养状况（日常饮食摄入模式）",
                 "options": [{"label": "1-非常差", "value": 1}, {"label": "2-可能不足", "value": 2}, {"label": "3-充足", "value": 3}, {"label": "4-极佳", "value": 4}]},
                {"id": "friction", "label": "摩擦力和剪切力",
                 "options": [{"label": "1-存在问题", "value": 1}, {"label": "2-潜在问题", "value": 2}, {"label": "3-无明显问题", "value": 3}]},
            ],
            "thresholds": [
                {"score": 9, "label": "🔴 高风险（≤9分，需立即采取预防措施）"},
                {"score": 12, "label": "🟠 中风险（10-12分，需加强预防）"},
                {"score": 14, "label": "🟡 轻度风险（13-14分，常规预防）"},
                {"score": 18, "label": "🟢 无风险（15-18分，标准护理）"},
                {"score": 23, "label": "🟢 无风险（19-23分，标准护理）"},
            ]
        },
        {
            "id": "morse",
            "title": "Morse跌倒风险评估量表",
            "items": [
                {"id": "fall_history", "label": "跌倒史（近3个月）",
                 "options": [{"label": "0-无", "value": 0}, {"label": "25-有", "value": 25}]},
                {"id": "secondary", "label": "合并其他诊断（≥2个医学诊断）",
                 "options": [{"label": "0-无", "value": 0}, {"label": "15-有", "value": 15}]},
                {"id": "aid", "label": "使用助行器",
                 "options": [{"label": "0-无/卧床/护士协助", "value": 0}, {"label": "15-拐杖/手杖/助步车", "value": 15}, {"label": "30-依靠家具行走", "value": 30}]},
                {"id": "iv", "label": "静脉输液/肝素锁",
                 "options": [{"label": "0-无", "value": 0}, {"label": "20-有", "value": 20}]},
                {"id": "gait", "label": "步态",
                 "options": [{"label": "0-正常/卧床", "value": 0}, {"label": "10-虚弱", "value": 10}, {"label": "20-障碍", "value": 20}]},
                {"id": "cognition", "label": "认知状态",
                 "options": [{"label": "0-了解自身能力", "value": 0}, {"label": "15-高估/忘记限制", "value": 15}]},
            ],
            "thresholds": [
                {"score": 24, "label": "🟢 低风险（0-24分，标准护理）"},
                {"score": 44, "label": "🟠 中风险（25-44分，需预防性措施）"},
                {"score": 125, "label": "🔴 高风险（≥45分，需立即执行跌倒预防措施）"},
            ]
        },
        {
            "id": "nrs",
            "title": "NRS数字疼痛评定量表（0-10分）",
            "items": [
                {"id": "pain", "label": "当前疼痛程度",
                 "options": [
                     {"label": "0-无疼痛", "value": 0}, {"label": "1", "value": 1}, {"label": "2", "value": 2},
                     {"label": "3-轻度", "value": 3}, {"label": "4", "value": 4}, {"label": "5-中度", "value": 5},
                     {"label": "6", "value": 6}, {"label": "7-重度", "value": 7}, {"label": "8", "value": 8},
                     {"label": "9", "value": 9}, {"label": "10-无法忍受", "value": 10}
                 ]},
            ],
            "thresholds": [
                {"score": 0, "label": "🟢 无疼痛"},
                {"score": 3, "label": "🟡 轻度疼痛（1-3分，非药物干预）"},
                {"score": 6, "label": "🟠 中度疼痛（4-6分，考虑药物干预）"},
                {"score": 10, "label": "🔴 重度疼痛（7-10分，需立即镇痛处理）"},
            ]
        },
        {
            "id": "nrs2002",
            "title": "NRS2002营养风险筛查量表",
            "items": [
                {"id": "ns", "label": "营养状态评分（体重/饮食/BMI）",
                 "options": [
                     {"label": "0-正常营养状态", "value": 0},
                     {"label": "1-3个月体重减轻5%或进食量50-75%", "value": 1},
                     {"label": "2-2个月体重减轻5%或BMI18.5-20.5+一般情况差", "value": 2},
                     {"label": "3-1个月体重减轻5%或BMI<18.5+一般情况差", "value": 3}
                 ]},
                {"id": "ds", "label": "疾病严重程度评分",
                 "options": [
                     {"label": "0-正常营养需要量", "value": 0},
                     {"label": "1-髋部骨折/慢性疾病急性发作", "value": 1},
                     {"label": "2-腹部手术/卒中/重度肺炎", "value": 2},
                     {"label": "3-头部损伤/骨髓移植/ICU", "value": 3}
                 ]},
                {"id": "age", "label": "年龄调整（≥70岁+1分）",
                 "options": [{"label": "0-否（<70岁）", "value": 0}, {"label": "1-是（≥70岁）", "value": 1}]},
            ],
            "thresholds": [
                {"score": 2, "label": "🟢 无营养风险（<3分，每周重复筛查）"},
                {"score": 7, "label": "🔴 存在营养风险（≥3分，需制定营养支持计划）"},
            ]
        },
        {
            "id": "barthel",
            "title": "Barthel日常生活活动能力指数（ADL）",
            "items": [
                {"id": "feeding", "label": "进食（使用餐具取食物入口）",
                 "options": [{"label": "0-完全依赖", "value": 0}, {"label": "5-需帮助", "value": 5}, {"label": "10-自理", "value": 10}]},
                {"id": "bathing", "label": "洗澡（含淋浴/盆浴）",
                 "options": [{"label": "0-依赖", "value": 0}, {"label": "5-自理", "value": 5}]},
                {"id": "grooming", "label": "修饰（洗脸/梳头/刷牙/刮脸）",
                 "options": [{"label": "0-依赖", "value": 0}, {"label": "5-自理", "value": 5}]},
                {"id": "dressing", "label": "穿衣（穿脱衣裤/系扣/系带）",
                 "options": [{"label": "0-依赖", "value": 0}, {"label": "5-需帮助", "value": 5}, {"label": "10-自理", "value": 10}]},
                {"id": "bowel", "label": "控制大便",
                 "options": [{"label": "0-失禁", "value": 0}, {"label": "5-偶尔失禁", "value": 5}, {"label": "10-可控制", "value": 10}]},
                {"id": "bladder", "label": "控制小便",
                 "options": [{"label": "0-失禁", "value": 0}, {"label": "5-偶尔失禁", "value": 5}, {"label": "10-可控制", "value": 10}]},
                {"id": "toilet", "label": "用厕（如厕/清洁/整理衣裤）",
                 "options": [{"label": "0-依赖", "value": 0}, {"label": "5-需帮助", "value": 5}, {"label": "10-自理", "value": 10}]},
                {"id": "transfer", "label": "床椅转移（床↔轮椅/椅）",
                 "options": [{"label": "0-不能", "value": 0}, {"label": "5-需大量帮助", "value": 5}, {"label": "10-需少量帮助", "value": 10}, {"label": "15-自理", "value": 15}]},
                {"id": "walking", "label": "平地行走45米",
                 "options": [{"label": "0-不能", "value": 0}, {"label": "5-需轮椅", "value": 5}, {"label": "10-需帮助", "value": 10}, {"label": "15-自理", "value": 15}]},
                {"id": "stairs", "label": "上下楼梯（10-15级台阶）",
                 "options": [{"label": "0-不能", "value": 0}, {"label": "5-需帮助", "value": 5}, {"label": "10-自理", "value": 10}]},
            ],
            "thresholds": [
                {"score": 20, "label": "🔴 极严重功能缺陷（<20分，完全依赖）"},
                {"score": 40, "label": "🟠 严重功能缺陷（20-40分，重度依赖）"},
                {"score": 60, "label": "🟡 中度功能缺陷（41-60分，中度依赖）"},
                {"score": 99, "label": "🟢 轻度功能缺陷（61-99分，轻度依赖）"},
                {"score": 100, "label": "🟢 ADL完全自理（100分）"},
            ]
        },
    ]


def generate_all_scales_v3(scale_definitions, pathway_days, now):
    """生成所有量表（支持多次记录）"""
    html = ""
    for scale_def in scale_definitions:
        scale_id = scale_def["id"]
        title = scale_def["title"]
        html += f'''<div class="scale-card">
          <div class="scale-card-header" onclick="toggleScale('{scale_id}')">
            <span>📊 {title}</span>
            <span style="font-size:11px;opacity:0.7">点击展开填写 ▼</span>
          </div>
          <div class="scale-card-body" id="{scale_id}_body">
            <div id="{scale_id}_records"></div>
          </div>
        </div>'''
    return html


def generate_operation_cards_v3(operation_points, diagnosis, pathway_days, now):
    """生成护理操作卡片（含操作要点核查 + 操作记录表，推荐日期基于临床路径）"""
    html = ""
    for op_idx, op in enumerate(operation_points):
        indications_html = "".join([f'<span class="tag green">{ind}</span>' for ind in (op.get("indications") or [])[:5]])
        contra_html = "".join([f'<span class="tag red">{c}</span>' for c in (op.get("contraindications") or [])[:5]])
        comp_html = "".join([f'<span class="tag blue">{c}</span>' for c in (op.get("complications") or [])[:6]])

        key_points_text = op.get("key_points", "")
        kp_items = [line.strip() for line in key_points_text.split("\n") if line.strip() and len(line.strip()) > 3]
        if not kp_items:
            kp_items = ["核对患者身份（两种以上方式核对）", "告知患者/家属操作目的及配合要点",
                        "洗手/手卫生（七步洗手法）", "准备用物（按医嘱）",
                        "执行操作（严格无菌原则）", "操作后评估效果", "操作后记录"]

        prep = op.get("preparations", {})

        # 生成操作核查清单HTML
        checklist_html = '<div>'
        for i, item in enumerate(kp_items):
            cb_id = f"chk_op{op_idx}_{i}"
            checklist_html += f'''<div class="checklist-item">
              <input type="checkbox" id="{cb_id}">
              <label for="{cb_id}">{item}</label>
            </div>'''
        checklist_html += '</div>'

        # 生成操作记录表HTML（推荐日期基于临床路径时间轴）
        record_table_html = f'''
        <div class="sub-header orange" style="margin-top:14px;display:flex;justify-content:space-between;align-items:center">
          📋 护理操作记录表
          <button class="btn btn-primary" style="font-size:11px;padding:4px 10px" onclick="addOperationRecord({op_idx})">➕ 添加操作记录</button>
        </div>
        <table class="op-record-table">
          <thead>
            <tr>
              <th style="width:35px">序号</th>
              <th>操作项目</th>
              <th style="width:80px">操作人员</th>
              <th style="width:90px">推荐操作日期</th>
              <th style="width:90px">实际操作时间</th>
              <th style="width:70px">操作结果</th>
              <th>备注/观察记录</th>
              <th style="width:50px">操作</th>
            </tr>
          </thead>
          <tbody id="op-record-tbody-{op_idx}">
        '''
        # 根据操作要点生成记录行，推荐日期均匀分布在临床路径天数内
        for i, kp in enumerate(kp_items[:8]):
            row_id = f"opr{op_idx}_{i}"
            # 推荐日期：将操作要点均匀分配到临床路径各天
            rec_day = min(i + 1, pathway_days)
            rec_date = (now + timedelta(days=rec_day - 1)).strftime("%Y-%m-%d")
            rec_date_display = f"D{rec_day} ({rec_date})"

            record_table_html += f'''<tr id="op-record-row-{op_idx}-{i}">
              <td style="text-align:center">{i+1}</td>
              <td style="font-size:11px"><input type="text" id="{row_id}_item" value="{kp}" style="width:100%;border:1px solid #ddd;padding:2px;font-size:11px"></td>
              <td><input type="text" id="{row_id}_operator" placeholder="签名"></td>
              <td><input type="date" id="{row_id}_rec_date" value="{rec_date}"><br><small style="font-size:9px;color:#888">{rec_date_display}</small></td>
              <td><input type="datetime-local" id="{row_id}_actual_time"></td>
              <td>
                <select id="{row_id}_result">
                  <option value="">--</option>
                  <option>完成</option><option>未完成</option><option>跳过</option>
                </select>
              </td>
              <td><input type="text" id="{row_id}_note" placeholder="备注" style="width:100%"></td>
              <td style="text-align:center"><button class="btn btn-danger" style="font-size:10px;padding:2px 6px" onclick="deleteOperationRecord({op_idx}, {i})">🗑️</button></td>
            </tr>'''
        record_table_html += '</tbody></table>'

        html += f'''<div class="std-card">
          <div class="std-card-header">
            <span>📄 {op.get("name", "护理操作")}</span>
            <span class="std-card-badge">{op.get("code", "")}</span>
          </div>
          <div class="std-card-body">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
              <div>
                <strong style="font-size:12px;color:#2e8b57">✅ 适应症</strong>
                <div class="tag-list">{indications_html if indications_html else '<span style="color:#888;font-size:12px">见标准文件</span>'}</div>
              </div>
              <div>
                <strong style="font-size:12px;color:#c0392b">⛔ 禁忌证</strong>
                <div class="tag-list">{contra_html if contra_html else '<span style="color:#888;font-size:12px">见标准文件</span>'}</div>
              </div>
            </div>

            <div class="sub-header" style="margin-top:8px">操作准备</div>
            <table style="font-size:12px">
              <tr><th style="width:80px">药物</th><td>{prep.get("drugs", "遵医嘱准备") or "遵医嘱准备"}</td></tr>
              <tr><th>器械/物品</th><td>{prep.get("equipment", "见标准文件") or "见标准文件"}</td></tr>
              <tr><th>患者准备</th><td>{prep.get("patient_prep", "向患者解释操作目的、方法及配合要点") or "向患者解释操作目的、方法及配合要点"}</td></tr>
            </table>

            <div class="sub-header" style="margin-top:12px">操作要点核查清单</div>
            {checklist_html}

            {record_table_html}

            <div class="sub-header orange" style="margin-top:12px">⚠️ 并发症监控</div>
            <div class="tag-list">{comp_html if comp_html else '<span style="color:#888;font-size:12px">见标准文件并发症章节</span>'}</div>

            {f'<div class="sub-header red" style="margin-top:8px">🚨 干预与处理措施</div><p style="font-size:12px;line-height:1.8">{op.get("interventions", "").replace(chr(10), "<br>")[:500]}</p>' if op.get("interventions") else ""}
            {f'<div class="sub-header" style="margin-top:8px">📌 注意事项</div><p style="font-size:12px">{op.get("precautions", "")[:300]}</p>' if op.get("precautions") else ""}
          </div>
        </div>'''
    return html


def generate_risk_cards(risks, pathway_days=7):
    """生成列表式风险因素清单（含登记功能）"""
    html = """<div style="margin-bottom:10px;font-size:11px;color:#666">
    <span>请在对应风险因素行登记「是否出现」及「发生日期」</span>
    </div>"""
    
    html += '<div style="overflow-x:auto"><table class="risk-table" style="width:100%;border-collapse:collapse;font-size:12px;table-layout:auto">'
    html += '<thead><tr style="background:#f0f4f8;font-weight:600">'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:left;min-width:40px">序号</th>'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:left;min-width:100px">风险项目名称</th>'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:left;min-width:80px">风险类型</th>'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:left;min-width:50px">阶段</th>'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:left;min-width:90px">监测值</th>'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:left;min-width:50px">风险级别</th>'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:left;min-width:120px">干预措施</th>'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:left;min-width:120px">处理措施</th>'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:center;min-width:40px">是否出现</th>'
    html += '<th style="border:1px solid #ccc;padding:6px;text-align:left;min-width:90px">发生日期</th>'
    html += '</tr></thead><tbody>'
    
    for idx, risk in enumerate(risks, 1):
        level_color = "#e74c3c" if "高" in risk.get("level", "") else "#f39c12" if "中" in risk.get("level", "") else "#27ae60"
        row_id = f"risk_{idx}"
        html += f'<tr id="{row_id}">'
        html += f'<td style="border:1px solid #ccc;padding:5px;text-align:center">{idx}</td>'
        html += f'<td style="border:1px solid #ccc;padding:5px;font-weight:600">{risk.get("name", "")}</td>'
        html += f'<td style="border:1px solid #ccc;padding:5px">{risk.get("type", "")}</td>'
        html += f'<td style="border:1px solid #ccc;padding:5px;text-align:center">{risk.get("stage", "")}</td>'
        html += f'<td style="border:1px solid #ccc;padding:5px;font-size:11px">{risk.get("monitor_value", "")}</td>'
        html += f'<td style="border:1px solid #ccc;padding:5px;text-align:center;color:{level_color};font-weight:700">{risk.get("level", "")}</td>'
        html += f'<td style="border:1px solid #ccc;padding:5px;font-size:11px">{risk.get("intervention", "")}</td>'
        html += f'<td style="border:1px solid #ccc;padding:5px;font-size:11px">{risk.get("handling", "")}</td>'
        html += f'<td style="border:1px solid #ccc;padding:5px;text-align:center"><input type="checkbox" id="{row_id}_occurred" onchange="toggleRiskRow(this)"></td>'
        html += f'<td style="border:1px solid #ccc;padding:5px"><input type="date" id="{row_id}_date" style="font-size:11px;width:95px" placeholder="发生日期"></td>'
        html += '</tr>'
    
    html += '</tbody></table></div>'
    return html


def main():
    parser = argparse.ArgumentParser(description="护理监护计划HTML生成器 v3.0")
    parser.add_argument("--diagnosis", required=True, help="患者诊断")
    parser.add_argument("--symptoms", default="", help="症状描述")
    parser.add_argument("--medications", default="", help="用药信息")
    parser.add_argument("--examinations", default="", help="检查检验信息")
    parser.add_argument("--patient_name", default="（患者姓名）", help="患者姓名")
    parser.add_argument("--nursing_level", default="一级护理",
                        choices=["特级护理", "一级护理", "二级护理", "三级护理"],
                        help="护理级别")
    parser.add_argument("--days", type=int, default=7, help="临床路径天数")
    parser.add_argument("--standards_json", default="", help="护理标准分析结果JSON路径（或JSON字符串）")
    parser.add_argument("--creator", default="责任护士", help="制定护士姓名")
    parser.add_argument("--department", default="护理单元", help="科室名称")
    parser.add_argument("--output", default="nursing_care_plan.html", help="输出HTML文件路径")
    args = parser.parse_args()

    standards = []
    if args.standards_json:
        if os.path.exists(args.standards_json):
            standards = load_standards(args.standards_json)
        else:
            try:
                standards = json.loads(args.standards_json)
            except Exception:
                pass

    normalized_standards = []
    for s in standards:
        if isinstance(s, dict):
            if "standard" in s:
                std_info = s.get("standard", {})
                analysis = s.get("analysis", {})
                merged = {**std_info, **analysis}
                merged["standard_name"] = std_info.get("name", "")
                merged["standard_code"] = std_info.get("code", "")
                normalized_standards.append(merged)
            else:
                normalized_standards.append(s)

    print(f"[INFO] 生成护理监护计划 v3.0: {args.diagnosis}")
    print(f"[INFO] 护理级别: {args.nursing_level}")
    print(f"[INFO] 临床路径: {args.days}天")
    print(f"[INFO] 引用标准数: {len(normalized_standards)}")

    html = generate_care_plan_html(
        diagnosis=args.diagnosis,
        symptoms=args.symptoms,
        medications=args.medications,
        examinations=args.examinations,
        patient_name=args.patient_name,
        nursing_level=args.nursing_level,
        pathway_days=args.days,
        standards=normalized_standards,
        creator=args.creator,
        department=args.department
    )

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[DONE] 护理监护计划已生成: {args.output}")
    print(f"[INFO] 文件大小: {len(html)//1024}KB")


if __name__ == "__main__":
    main()
