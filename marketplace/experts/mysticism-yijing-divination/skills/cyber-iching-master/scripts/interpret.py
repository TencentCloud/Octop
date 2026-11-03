#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cyber I Ching Master — 义理生成器 (Interpretation Engine)
象 → 数 → 理 三层解读系统

融合卦象图像、五行数理与义理哲学，提供完整的易经解读服务。
支持与八字模块联动，实现命理与易理的深度结合。
"""

import json
import os
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime


# 八卦完整信息
TRIGRAMS = {
    '000': {
        'name': '乾', 'symbol': '☰', 'wu_xing': '金',
        'meaning': '天', 'nature': '刚健', 'direction': '西北',
        'family': '父', 'body': '首', 'season': '秋冬间',
        'keywords': ['创造', '刚健', '进取', '领导', '权威']
    },
    '001': {
        'name': '兑', 'symbol': '☱', 'wu_xing': '金',
        'meaning': '泽', 'nature': '喜悦', 'direction': '西',
        'family': '少女', 'body': '口', 'season': '秋',
        'keywords': ['交流', '愉悦', '口才', '情感', '和谐']
    },
    '010': {
        'name': '离', 'symbol': '☲', 'wu_xing': '火',
        'meaning': '火', 'nature': '光明', 'direction': '南',
        'family': '中女', 'body': '目', 'season': '夏',
        'keywords': ['智慧', '文明', '热情', '洞察', '礼仪']
    },
    '011': {
        'name': '震', 'symbol': '☳', 'wu_xing': '木',
        'meaning': '雷', 'nature': '震动', 'direction': '东',
        'family': '长男', 'body': '足', 'season': '春',
        'keywords': ['行动', '果断', '勇气', '振作', '领袖']
    },
    '100': {
        'name': '巽', 'symbol': '☴', 'wu_xing': '木',
        'meaning': '风', 'nature': '入', 'direction': '东南',
        'family': '长女', 'body': '股', 'season': '春夏间',
        'keywords': ['顺从', '谦逊', '渗透', '灵活', '商贾']
    },
    '101': {
        'name': '坎', 'symbol': '☵', 'wu_xing': '水',
        'meaning': '水', 'nature': '险陷', 'direction': '北',
        'family': '中男', 'body': '耳', 'season': '冬',
        'keywords': ['智慧', '危险', '变化', '隐伏', '忍耐']
    },
    '110': {
        'name': '艮', 'symbol': '☶', 'wu_xing': '土',
        'meaning': '山', 'nature': '停止', 'direction': '东北',
        'family': '少男', 'body': '手', 'season': '冬春间',
        'keywords': ['稳定', '停止', '保守', '诚信', '笃实']
    },
    '111': {
        'name': '坤', 'symbol': '☷', 'wu_xing': '土',
        'meaning': '地', 'nature': '柔顺', 'direction': '西南',
        'family': '母', 'body': '腹', 'season': '夏秋间',
        'keywords': ['承载', '柔顺', '包容', '厚德', '奉献']
    }
}

# 五行生克关系
WU_XING_RELATIONS = {
    '木': {'生': '火', '克': '土', '被生': '水', '被克': '金'},
    '火': {'生': '土', '克': '金', '被生': '木', '被克': '水'},
    '土': {'生': '金', '克': '水', '被生': '火', '被克': '木'},
    '金': {'生': '水', '克': '木', '被生': '土', '被克': '火'},
    '水': {'生': '木', '克': '火', '被生': '金', '被克': '土'}
}

# 问题类型映射
QUESTION_TYPES = {
    '事业': ['工作', '事业', '创业', '求职', '晋升', '事业'],
    '感情': ['感情', '姻缘', '婚姻', '恋爱', '桃花', '复合'],
    '财运': ['财运', '钱', '投资', '生意', '理财', '财富'],
    '健康': ['健康', '病', '身体', '养生', '疾病'],
    '学业': ['学业', '考试', '学习', '升学', '论文'],
    '出行': ['出行', '旅游', '搬家', '迁移', '远行'],
    '人际': ['人际', '小人', '贵人', '关系', '合作']
}


@dataclass
class YaoInterpretation:
    """爻解读数据类"""
    position: int
    line_name: str
    ci: str           # 爻辞
    xiang: str        # 小象传
    yiyi: str         # 现代义译
    wu_xing: str      # 本爻五行
    position_meaning: str  # 爻位含义


class InterpretationEngine:
    """
    义理生成器核心类
    
    提供"象→数→理"三层解读：
    - 象层：卦象图像、爻象变化
    - 数层：五行数理、卦气旺衰
    - 理层：义理哲学、处世之道
    """
    
    def __init__(self, hexagram_db_path: str = None):
        """初始化解读引擎"""
        self.hexagram_db = {}
        self.yao_templates = {}  # 爻辞模板
        
        if hexagram_db_path and os.path.exists(hexagram_db_path):
            self._load_data(hexagram_db_path)
        else:
            # 尝试默认路径
            default_path = os.path.join(
                os.path.dirname(__file__), 'data', 'hexagrams.json'
            )
            if os.path.exists(default_path):
                self._load_data(default_path)
    
    def _load_data(self, path: str):
        """加载卦象数据库"""
        with open(path, 'r', encoding='utf-8') as f:
            self.hexagram_db = json.load(f)
    
    def get_hexagram_data(self, binary_code: str) -> Dict:
        """获取卦象完整数据"""
        return self.hexagram_db.get(binary_code, {})
    
    def _get_trigram(self, code: str) -> Dict:
        """获取八卦信息"""
        return TRIGRAMS.get(code, {})
    
    def _determine_wu_xing(self, yao_value: int, upper_wu_xing: str) -> str:
        """根据爻的位置和阴阳确定五行"""
        # 阳爻继承上卦五行，阴爻生上卦五行
        if yao_value == 0:  # 阳爻
            return upper_wu_xing
        else:  # 阴爻
            return WU_XING_RELATIONS.get(upper_wu_xing, {}).get('被生', '土')
    
    def _get_position_meaning(self, position: int, is_yang: bool) -> str:
        """获取爻位含义"""
        meanings = {
            1: {'yang': '潜龙勿用 - 初难知，蕴含生机', 
                'yin': '履霜坚冰至 - 阴始凝而履霜'},
            2: {'yang': '见龙在田 - 二多誉，德施普也',
                'yin': '直方大 - 地道光也，含章可贞'},
            3: {'yang': '乾乾夕惕 - 三多凶，夕惕若厉',
                'yin': '含章可贞 - 三少阳，慎不败也'},
            4: {'yang': '或跃在渊 - 四多惧，进退可变',
                'yin': '括囊无咎 - 四阴柔，谨言慎行'},
            5: {'yang': '飞龙在天 - 五多功，大人造也',
                'yin': '黄裳元吉 - 五阴柔，居中守正'},
            6: {'yang': '亢龙有悔 - 上易知，盈不可久',
                'yin': '龙战于野 - 上六阴盛，阳尽阴极'}
        }
        key = 'yang' if is_yang else 'yin'
        return meanings.get(position, {}).get(key, '爻位待解')
    
    def _build_yao_interpretation(self, yao_data: Dict, position: int, 
                                   upper_wu_xing: str, binary_code: str = '') -> YaoInterpretation:
        """构建爻解读对象"""
        # 从卦码推断阴阳：0=阳(九)，1=阴(六)
        is_yang = len(binary_code) == 6 and binary_code[position - 1] == '0'
        
        pos_label = ['初', '二', '三', '四', '五', '上'][position - 1]
        yin_yang = '九' if is_yang else '六'
        # 爻名格式：初爻=初九，上爻=上九，其他=九二~九五
        if position == 1 or position == 6:
            line_str = yao_data.get('line', f'{pos_label}{yin_yang}')
        else:
            line_str = yao_data.get('line', f'{yin_yang}{pos_label}')
        
        return YaoInterpretation(
            position=position,
            line_name=line_str,
            ci=yao_data.get('ci', yao_data.get('text', '（待补）')),
            xiang=yao_data.get('xiang', '（待补）'),
            yiyi=yao_data.get('yiyi', '（待补）'),
            wu_xing=self._determine_wu_xing(0 if is_yang else 1, upper_wu_xing),
            position_meaning=self._get_position_meaning(position, is_yang)
        )
    
    # ========== 象层解读 ==========
    
    def interpret_xiang(self, binary_code: str) -> str:
        """
        象层解读：卦象图像分析
        
        分析卦的上下结构、爻象变化、卦象组合
        """
        hex_data = self.get_hexagram_data(binary_code)
        if not hex_data:
            return "【象层】数据缺失"
        
        lines = []
        lines.append("━━━ 【象层】卦象图像 ━━━")
        lines.append("")
        
        # 卦名与结构
        name = hex_data.get('name', '?')
        pinyin = hex_data.get('pinyin', '')
        full_name = hex_data.get('full_name', '')
        
        lines.append(f"【本卦】{name}（{pinyin}）")
        lines.append(f"【结构】{full_name}")
        lines.append("")
        
        # 上下卦分析（兼容新旧结构）
        upper_code = hex_data.get('upper_trigram', {}).get('code', '') if isinstance(hex_data.get('upper_trigram'), dict) else hex_data.get('upper_trigram_code', '')
        lower_code = hex_data.get('lower_trigram', {}).get('code', '') if isinstance(hex_data.get('lower_trigram'), dict) else hex_data.get('lower_trigram_code', '')
        upper_name = hex_data.get('upper_trigram', {}).get('name', '') if isinstance(hex_data.get('upper_trigram'), dict) else hex_data.get('upper_trigram_name', '')
        lower_name = hex_data.get('lower_trigram', {}).get('name', '') if isinstance(hex_data.get('lower_trigram'), dict) else hex_data.get('lower_trigram_name', '')
        
        lines.append("【卦象构成】")
        lines.append(f"  上卦 {TRIGRAMS.get(upper_code, {}).get('symbol', '?')} {upper_name} — {TRIGRAMS.get(upper_code, {}).get('meaning', '')}")
        lines.append(f"  下卦 {TRIGRAMS.get(lower_code, {}).get('symbol', '?')} {lower_name} — {TRIGRAMS.get(lower_code, {}).get('meaning', '')}")
        lines.append("")
        
        # 象意解读
        lines.append("【象意分析】")
        upper_info = TRIGRAMS.get(upper_code, {})
        lower_info = TRIGRAMS.get(lower_code, {})
        
        lines.append(f"  {upper_name}覆{lower_name}：{upper_info.get('nature', '')}而{lower_info.get('nature', '')}")
        lines.append(f"  上者{upper_info.get('wu_xing', '')}，下者{WU_XING_RELATIONS.get(upper_info.get('wu_xing', ''), {}).get('生', '')}之")
        lines.append("")
        
        # 家庭象喻
        lines.append("【家庭象喻】")
        family_map = {
            '乾': '父亲', '坤': '母亲', '震': '长男', '巽': '长女',
            '坎': '中男', '离': '中女', '艮': '少男', '兑': '少女'
        }
        lines.append(f"  {family_map.get(upper_name, '?')}在上，{family_map.get(lower_name, '?')}在下")
        lines.append("")
        
        return '\n'.join(lines)
    
    # ========== 数层解读 ==========
    
    def interpret_shu(self, binary_code: str, changing_yao: List[int] = None,
                      bazi_data: Dict = None) -> str:
        """
        数层解读：五行数理分析
        
        分析卦气旺衰、五行生克、数理变化
        """
        hex_data = self.get_hexagram_data(binary_code)
        if not hex_data:
            return "【数层】数据缺失"
        
        lines = []
        lines.append("━━━ 【数层】五行数理 ━━━")
        lines.append("")
        
        # 上下卦五行（兼容新旧结构）
        upper_code = hex_data.get('upper_trigram', {}).get('code', '') if isinstance(hex_data.get('upper_trigram'), dict) else hex_data.get('upper_trigram_code', '')
        lower_code = hex_data.get('lower_trigram', {}).get('code', '') if isinstance(hex_data.get('lower_trigram'), dict) else hex_data.get('lower_trigram_code', '')
        upper_name = hex_data.get('upper_trigram', {}).get('name', '') if isinstance(hex_data.get('upper_trigram'), dict) else hex_data.get('upper_trigram_name', '')
        lower_name = hex_data.get('lower_trigram', {}).get('name', '') if isinstance(hex_data.get('lower_trigram'), dict) else hex_data.get('lower_trigram_name', '')
        
        upper_wu_xing = TRIGRAMS.get(upper_code, {}).get('wu_xing', '土')
        lower_wu_xing = TRIGRAMS.get(lower_code, {}).get('wu_xing', '土')
        
        lines.append("【五行配置】")
        lines.append(f"  上卦 {upper_name} 属 {upper_wu_xing} {'（旺）' if upper_wu_xing in ['木', '火'] else '（相）'}")
        lines.append(f"  下卦 {lower_name} 属 {lower_wu_xing} {'（旺）' if lower_wu_xing in ['木', '火'] else '（相）'}")
        lines.append("")
        
        # 五行生克
        lines.append("【五行关系】")
        if upper_wu_xing == lower_wu_xing:
            lines.append(f"  同气相求：{upper_wu_xing}与{lower_wu_xing}相助，气势和谐")
        else:
            sheng = WU_XING_RELATIONS.get(upper_wu_xing, {}).get('生', '')
            ke = WU_XING_RELATIONS.get(upper_wu_xing, {}).get('克', '')
            if lower_wu_xing == sheng:
                lines.append(f"  上卦{upper_wu_xing}生下卦{lower_wu_xing}：生气流通")
            elif lower_wu_xing == ke:
                lines.append(f"  上卦{upper_wu_xing}克下卦{lower_wu_xing}：刚柔相济")
            else:
                lines.append(f"  {upper_wu_xing}与{lower_wu_xing}：同处不同气")
        lines.append("")
        
        # 变爻数理
        if changing_yao:
            lines.append(f"【变爻分析】第{', '.join(map(str, changing_yao))}爻为动爻")
            lines.append("  动爻转换阴阳，五行随之变化")
            lines.append("  变爻所在位置决定事体主次")
            lines.append("")
        
        # 八字联动（如有）
        if bazi_data:
            lines.append("【命理联动】")
            lines.append(f"  命主五行：{bazi_data.get('day_master', '?')}（日主）")
            lines.append(f"  卦象五行与命局相互参照")
            lines.append("")
        
        return '\n'.join(lines)
    
    # ========== 理层解读 ==========
    
    def interpret_li(self, binary_code: str, question: str = "",
                     changing_yao: List[int] = None) -> str:
        """
        理层解读：义理哲学分析
        
        分析卦辞彖传、处世之道、针对性建议
        """
        hex_data = self.get_hexagram_data(binary_code)
        if not hex_data:
            return "【理层】数据缺失"
        
        lines = []
        lines.append("━━━ 【理层】义理哲学 ━━━")
        lines.append("")
        
        name = hex_data.get('name', '?')
        lines.append(f"【卦名要义】{name}")
        lines.append("")
        
        # 卦辞
        gua_ci = hex_data.get('gua_ci', '')
        if gua_ci:
            lines.append("【卦辞】")
            lines.append(f"  {gua_ci}")
            lines.append("")
        
        # 彖传
        tuan = hex_data.get('tuan', '')
        if tuan:
            lines.append("【彖传】解义")
            lines.append(f"  {tuan}")
            lines.append("")
        
        # 大象
        xiang = hex_data.get('xiang_da', '') or hex_data.get('xiang', '')
        if xiang:
            lines.append("【大象】")
            lines.append(f"  {xiang}")
            lines.append("")
        
        # 问事针对性解读
        if question:
            q_type = self._identify_question_type(question)
            if q_type:
                lines.append(f"【{q_type}解】")
                advice = self._generate_advice(binary_code, q_type, changing_yao)
                lines.append(f"  {advice}")
                lines.append("")
        
        return '\n'.join(lines)
    
    def _identify_question_type(self, question: str) -> Optional[str]:
        """识别问题类型"""
        q = question.lower()
        for qtype, keywords in QUESTION_TYPES.items():
            if any(k in q for k in keywords):
                return qtype
        return None
    
    def _generate_advice(self, binary_code: str, q_type: str, 
                         changing_yao: List[int] = None) -> str:
        """生成针对性建议"""
        # 基于卦象特性和问题类型生成建议
        advice_templates = {
            '事业': "当顺势而为，以刚健进取之心处世。注意把握时机，不可冒进。",
            '感情': "感情之事贵在真诚相待，阴阳和合方能长久。",
            '财运': "财运营生需审时度势，积少成多，不可贪心。",
            '健康': "修身养性，顺应天时，保养正气，邪不可干。",
            '学业': "学问之道贵在持之以恒，日新又新，方能精进。",
            '出行': "出行需择吉日良时，事前详加筹划方为上策。",
            '人际': "与人相处以诚为本，广结善缘，自有贵人相助。"
        }
        
        base_advice = advice_templates.get(q_type, "审时度势，顺其自然。")
        
        # 根据变爻调整建议
        if changing_yao:
            if 1 in changing_yao or 2 in changing_yao:
                return "【初爻变】" + base_advice + "万事开头难，需谨慎起步。"
            elif 3 in changing_yao or 4 in changing_yao:
                return "【中爻变】" + base_advice + "事至中途，戒骄戒躁，守正持中。"
            elif 5 in changing_yao or 6 in changing_yao:
                return "【上爻变】" + base_advice + "事已近成，当知进退，不可强求。"
        
        return base_advice
    
    # ========== 爻辞解读 ==========
    
    def interpret_yao_detail(self, binary_code: str, changing_yao: List[int] = None) -> str:
        """
        爻辞详解
        
        逐爻分析爻辞、小象、义译
        """
        hex_data = self.get_hexagram_data(binary_code)
        if not hex_data or 'yaos' not in hex_data:
            return "【爻辞】数据缺失"
        
        lines = []
        lines.append("━━━ 【爻辞详解】 ━━━")
        lines.append("")
        
        upper_code = hex_data.get('upper_trigram', {}).get('code', '') if isinstance(hex_data.get('upper_trigram'), dict) else hex_data.get('upper_trigram_code', '')
        upper_wu_xing = TRIGRAMS.get(upper_code, {}).get('wu_xing', '土')
        
        yaos_raw = hex_data.get('yaos', {})
        
        # 统一处理 list 和 dict 格式
        if isinstance(yaos_raw, dict):
            yaos = [(int(k), v) for k, v in sorted(yaos_raw.items(), key=lambda x: int(x[0]))]
        else:
            yaos = [(i+1, v) for i, v in enumerate(yaos_raw)]
        
        # 乾卦特殊处理：用九
        if binary_code == '000000':
            yj = hex_data.get('yong_jiu')
            if yj:
                lines.append("【用九】" + yj.get('ci', ''))
                lines.append("  小象：" + yj.get('xiang', ''))
                lines.append("  义译：" + yj.get('yiyi', ''))
                lines.append("")
        
        for i, yao in yaos[:6]:
            pos_label = ['初', '二', '三', '四', '五', '上'][i-1]
            yao_interp = self._build_yao_interpretation(yao, i, upper_wu_xing, binary_code)
            is_changing = changing_yao and i in changing_yao
            
            marker = " ←【动】" if is_changing else ""
            lines.append(f"【第{i}爻 {pos_label}】{yao_interp.line_name}{marker}")
            lines.append(f"  爻辞：{yao_interp.ci}")
            
            xiang = yao.get('xiang', '')
            if xiang:
                lines.append(f"  小象：{xiang}")
            
            yiyi = yao.get('yiyi', '')
            if yiyi:
                lines.append(f"  义译：{yiyi}")
            
            lines.append(f"  爻位：{yao_interp.position_meaning}")
            lines.append("")
        
        # 坤卦特殊处理：用六
        if binary_code == '111111':
            yl = hex_data.get('yong_liu')
            if yl:
                lines.append("【用六】" + yl.get('ci', ''))
                lines.append("  小象：" + yl.get('xiang', ''))
                lines.append("  义译：" + yl.get('yiyi', ''))
                lines.append("")
        
        return '\n'.join(lines)
    
    # ========== 综合解读 ==========
    
    def generate_full_interpretation(self, binary_code: str, 
                                      question: str = "",
                                      changing_yao: List[int] = None,
                                      bazi_data: Dict = None,
                                      show_yao_detail: bool = True) -> str:
        """
        生成完整的三层解读报告
        
        Args:
            binary_code: 六位二进制卦码
            question: 所问之事
            changing_yao: 变爻列表
            bazi_data: 八字数据（可选）
            show_yao_detail: 是否显示爻辞详解
        
        Returns:
            str: 完整解读文本
        """
        hex_data = self.get_hexagram_data(binary_code)
        if not hex_data:
            return f"错误：未找到卦象数据 {binary_code}"
        
        lines = []
        
        # 标题
        lines.append("╔══════════════════════════════════════╗")
        lines.append("║     ☯️ Cyber I Ching Master            ║")
        lines.append("║     象 → 数 → 理 三层解读             ║")
        lines.append("╚══════════════════════════════════════╝")
        lines.append("")
        
        # 基本信息
        name = hex_data.get('name', '?')
        pinyin = hex_data.get('pinyin', '')
        full_name = hex_data.get('full_name', '')
        
        lines.append(f"【本卦】{name}（{pinyin}）{full_name}")
        if question:
            lines.append(f"【所问】{question}")
        if changing_yao:
            lines.append(f"【动爻】第{', '.join(map(str, changing_yao))}爻")
        lines.append("")
        
        # 象层
        lines.append(self.interpret_xiang(binary_code))
        lines.append("")
        
        # 数层
        lines.append(self.interpret_shu(binary_code, changing_yao, bazi_data))
        lines.append("")
        
        # 爻辞详解
        if show_yao_detail:
            lines.append(self.interpret_yao_detail(binary_code, changing_yao))
            lines.append("")
        
        # 理层
        lines.append(self.interpret_li(binary_code, question, changing_yao))
        lines.append("")
        
        # 总结
        lines.append("━━━ 【综合论断】 ━━━")
        summary = self._generate_summary(binary_code, question, changing_yao)
        lines.append(summary)
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("卦象已存入底层逻辑，随时可供回溯。")
        lines.append("算法虽定，人为变量存疑，汝其慎之。")
        
        return '\n'.join(lines)
    
    def _generate_summary(self, binary_code: str, question: str = "",
                          changing_yao: List[int] = None) -> str:
        """生成综合论断"""
        hex_data = self.get_hexagram_data(binary_code)
        name = hex_data.get('name', '?')
        gua_ci = hex_data.get('gua_ci', '')
        xiang = hex_data.get('xiang_da', '') or hex_data.get('xiang', '')
        
        lines = []
        lines.append(f"卦象核心：{name}——{gua_ci[:20] if gua_ci else ''}...")
        lines.append(f"行事准则：{xiang[:20] if xiang else ''}...")
        
        if changing_yao:
            lines.append(f"关键在第{changing_yao[0]}爻：事物发展的转折点")
        
        return '\n'.join(lines)
    
    # ========== 变卦解读 ==========
    
    def interpret_changed_hexagram(self, original: str, changed: str,
                                    changing_yao: List[int]) -> str:
        """解读本卦与变卦的关系"""
        lines = []
        lines.append("━━━ 【本卦之卦】 ━━━")
        lines.append("")
        
        orig_data = self.get_hexagram_data(original)
        changed_data = self.get_hexagram_data(changed)
        
        if orig_data and changed_data:
            lines.append(f"本卦：{orig_data.get('name', '?')} → 之卦：{changed_data.get('name', '?')}")
            lines.append(f"由{len(changing_yao)}爻变化所致")
            lines.append("")
            
            # 变化分析
            lines.append("【变化趋势】")
            if len(changing_yao) == 1:
                lines.append("单爻变动，局势微调，需耐心等待时机。")
            elif len(changing_yao) <= 3:
                lines.append("多爻变化，局势将发生明显转变。")
            else:
                lines.append("大量爻变，事物将发生根本性转变。")
            lines.append("")
        
        return '\n'.join(lines)
    
    # ========== 快捷方法 ==========
    
    def quick_read(self, binary_code: str) -> str:
        """快速读卦"""
        hex_data = self.get_hexagram_data(binary_code)
        if not hex_data:
            return f"未找到卦象：{binary_code}"
        
        lines = []
        lines.append(f"【{hex_data.get('name', '?')}】{hex_data.get('full_name', '')}")
        lines.append(f"卦辞：{hex_data.get('gua_ci', '')}")
        lines.append(f"大象：{hex_data.get('xiang_da', '') or hex_data.get('xiang', '')}")
        
        return '\n'.join(lines)


# CLI 入口
if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Cyber I Ching Master — 义理生成器'
    )
    parser.add_argument('--hexagram', '-g', help='六位二进制卦码')
    parser.add_argument('--question', '-q', default='', help='所问之事')
    parser.add_argument('--changing', '-c', nargs='*', type=int, help='变爻位置')
    parser.add_argument('--data', '-d', default='', help='卦数据库路径')
    parser.add_argument('--level', '-l', choices=['full', 'xiang', 'shu', 'li', 'quick'],
                       default='full', help='解读层级')
    
    args = parser.parse_args()
    
    engine = InterpretationEngine(args.data if args.data else None)
    
    if args.hexagram:
        if args.level == 'quick':
            print(engine.quick_read(args.hexagram))
        elif args.level == 'xiang':
            print(engine.interpret_xiang(args.hexagram))
        elif args.level == 'shu':
            print(engine.interpret_shu(args.hexagram, args.changing))
        elif args.level == 'li':
            print(engine.interpret_li(args.hexagram, args.question, args.changing))
        else:
            print(engine.generate_full_interpretation(
                args.hexagram, args.question, args.changing
            ))
    else:
        print("请提供卦码：--hexagram 000000")
        print("示例：python interpret.py -g 000000 -q 事业")
