#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cyber I Ching Master — Core Engine
赛博易经大师 · 起卦核心引擎
"""

import random
import json
import os
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict
from enum import Enum
from datetime import datetime


class LineType(Enum):
    """爻类型"""
    YOUNG_YANG = 0   # 少阳 ⚊
    YOUNG_YIN = 1    # 少阴 ⚋
    OLD_YANG = 2     # 老阳 ⚊ ✦
    OLD_YIN = 3      #老阴 ⚋ ✦


@dataclass
class Yao:
    """单爻"""
    position: int
    line_type: LineType
    is_changing: bool
    
    @property
    def value(self) -> int:
        return 0 if self.line_type in (LineType.YOUNG_YANG, LineType.OLD_YANG) else 1
    
    @property
    def changed_value(self) -> int:
        return 1 - self.value if self.is_changing else self.value
    
    def __str__(self):
        symbols = {
            LineType.YOUNG_YANG: "━━━━━━━",
            LineType.YOUNG_YIN: "━━ ━━",
            LineType.OLD_YANG: "━━━━━━━ ✦",
            LineType.OLD_YIN: "━━ ━━ ✦"
        }
        pos_names = ["初", "二", "三", "四", "五", "上"]
        return f"{pos_names[self.position-1]}  {symbols[self.line_type]}"


@dataclass
class Hexagram:
    """卦象"""
    name: str
    chinese_name: str
    upper_trigram: str
    lower_trigram: str
    upper_trigram_code: str
    lower_trigram_code: str
    yao_list: List[Yao]
    changing_yao: List[int]
    question: str = ""
    method: str = ""
    timestamp: str = ""
    
    @property
    def binary_code(self) -> str:
        return ''.join(str(y.value) for y in self.yao_list)
    
    @property
    def changed_binary(self) -> str:
        return ''.join(str(y.changed_value) for y in self.yao_list)
    
    def get_trigram_name(self, code: str) -> str:
        trigrams = {
            '000': '☰ 乾', '001': '☱ 兑', '010': '☲ 离', '011': '☳ 震',
            '100': '☴ 巽', '101': '☵ 坎', '110': '☶ 艮', '111': '☷ 坤'
        }
        return trigrams.get(code, '未知')
    
    def display(self) -> str:
        lines = []
        upper = ''.join(str(y.value) for y in self.yao_list[3:6])
        lines.append(f"    {self.get_trigram_name(upper)}（上卦/外卦）")
        lines.append("    ═══════════════")
        
        for i in range(5, -1, -1):
            yao = self.yao_list[i]
            line = "━━━━━━━" if yao.value == 0 else "━━ ━━"
            marker = "  ← 变" if yao.is_changing else ""
            pos_name = ["上", "五", "四", "三", "二", "初"][5-i]
            lines.append(f"{pos_name}  {line}{marker}")
        
        lower = ''.join(str(y.value) for y in self.yao_list[0:3])
        lines.append("    ═══════════════")
        lines.append(f"    {self.get_trigram_name(lower)}（下卦/内卦）")
        
        return '\n'.join(lines)
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'chinese_name': self.chinese_name,
            'upper_trigram': self.upper_trigram,
            'lower_trigram': self.lower_trigram,
            'upper_trigram_code': self.upper_trigram_code,
            'lower_trigram_code': self.lower_trigram_code,
            'binary_code': self.binary_code,
            'changed_binary': self.changed_binary,
            'changing_yao': self.changing_yao,
            'question': self.question,
            'method': self.method,
            'timestamp': self.timestamp,
            'yao_list': [
                {
                    'position': y.position,
                    'line_type': y.line_type.name,
                    'is_changing': y.is_changing,
                    'value': y.value,
                    'changed_value': y.changed_value
                }
                for y in self.yao_list
            ]
        }


class CyberIChingMaster:
    """赛博易经大师 · 核心引擎"""
    
    # 二进制到卦名映射（全部64卦）
    HEXAGRAM_NAMES = {
        '000000': ('乾', 'qián', '乾为天'),
        '000001': ('夬', 'guài', '泽天夬'),
        '000010': ('大有', 'dà yǒu', '火天大有'),
        '000011': ('大壮', 'dà zhuàng', '雷天大壮'),
        '000100': ('小畜', 'xiǎo chù', '风天小畜'),
        '000101': ('需', 'xū', '水天需'),
        '000110': ('大畜', 'dà chù', '山天大畜'),
        '000111': ('泰', 'tài', '地天泰'),
        '001000': ('履', 'lǚ', '天泽履'),
        '001001': ('兑', 'duì', '兑为泽'),
        '001010': ('睽', 'kuí', '火泽睽'),
        '001011': ('归妹', 'guī mèi', '雷泽归妹'),
        '001100': ('中孚', 'zhōng fú', '风泽中孚'),
        '001101': ('节', 'jié', '水泽节'),
        '001110': ('损', 'sǔn', '山泽损'),
        '001111': ('临', 'lín', '地泽临'),
        '010000': ('同人', 'tóng rén', '天火同人'),
        '010001': ('革', 'gé', '泽火革'),
        '010010': ('离', 'lí', '离为火'),
        '010011': ('丰', 'fēng', '雷火丰'),
        '010100': ('家人', 'jiā rén', '风火家人'),
        '010101': ('既济', 'jì jì', '水火既济'),
        '010110': ('贲', 'bì', '山火贲'),
        '010111': ('明夷', 'míng yí', '地火明夷'),
        '011000': ('无妄', 'wú wàng', '天雷无妄'),
        '011001': ('随', 'suí', '泽雷随'),
        '011010': ('噬嗑', 'shì kē', '火雷噬嗑'),
        '011011': ('震', 'zhèn', '震为雷'),
        '011100': ('益', 'yì', '风雷益'),
        '011101': ('屯', 'tún', '水雷屯'),
        '011110': ('颐', 'yí', '山雷颐'),
        '011111': ('复', 'fù', '地雷复'),
        '100000': ('姤', 'gòu', '天风姤'),
        '100001': ('大过', 'dà guò', '泽风大过'),
        '100010': ('鼎', 'dǐng', '火风鼎'),
        '100011': ('恒', 'héng', '雷风恒'),
        '100100': ('巽', 'xùn', '巽为风'),
        '100101': ('蛊', 'gǔ', '风水蛊'),
        '100110': ('升', 'shēng', '地风升'),
        '100111': ('讼', 'sòng', '天水讼'),
        '101000': ('遁', 'dùn', '天山遁'),
        '101001': ('咸', 'xián', '泽山咸'),
        '101010': ('旅', 'lǚ', '火山旅'),
        '101011': ('小过', 'xiǎo guò', '雷山小过'),
        '101100': ('渐', 'jiàn', '风山渐'),
        '101101': ('蹇', 'jiǎn', '水山蹇'),
        '101110': ('谦', 'qiān', '地山谦'),
        '101111': ('否', 'pǐ', '天地否'),
        '110000': ('萃', 'cuì', '泽地萃'),
        '110001': ('晋', 'jìn', '火地晋'),
        '110010': ('坤', 'kūn', '坤为地'),
        '110011': ('豫', 'yù', '雷地豫'),
        '110100': ('观', 'guān', '风地观'),
        '110101': ('比', 'bǐ', '水地比'),
        '110110': ('剥', 'bō', '山地剥'),
        '110111': ('师', 'shī', '地水师'),
        '111000': ('比', 'bǐ', '水地比'),
        '111001': ('剥', 'bō', '山地剥'),
        '111010': ('蛊', 'gǔ', '山风蛊'),
        '111011': ('困', 'kùn', '泽水困'),
        '111100': ('井', 'jǐng', '水风井'),
        '111101': ('坎', 'kǎn', '坎为水'),
        '111110': ('蒙', 'méng', '山水蒙'),
        '111111': ('师', 'shī', '地水师'),
    }
    
    # 正确映射所有64卦
    FULL_HEXAGRAM_MAP = {
        '000000': ('乾', 'qián', '乾为天', '乾', '乾'),
        '000001': ('夬', 'guài', '泽天夬', '兑', '乾'),
        '000010': ('大有', 'dà yǒu', '火天大有', '离', '乾'),
        '000011': ('大壮', 'dà zhuàng', '雷天大壮', '震', '乾'),
        '000100': ('小畜', 'xiǎo chù', '风天小畜', '巽', '乾'),
        '000101': ('需', 'xū', '水天需', '坎', '乾'),
        '000110': ('大畜', 'dà chù', '山天大畜', '艮', '乾'),
        '000111': ('泰', 'tài', '地天泰', '坤', '乾'),
        '001000': ('履', 'lǚ', '天泽履', '乾', '兑'),
        '001001': ('兑', 'duì', '兑为泽', '兑', '兑'),
        '001010': ('睽', 'kuí', '火泽睽', '离', '兑'),
        '001011': ('归妹', 'guī mèi', '雷泽归妹', '震', '兑'),
        '001100': ('中孚', 'zhōng fú', '风泽中孚', '巽', '兑'),
        '001101': ('节', 'jié', '水泽节', '坎', '兑'),
        '001110': ('损', 'sǔn', '山泽损', '艮', '兑'),
        '001111': ('临', 'lín', '地泽临', '坤', '兑'),
        '010000': ('同人', 'tóng rén', '天火同人', '乾', '离'),
        '010001': ('革', 'gé', '泽火革', '兑', '离'),
        '010010': ('离', 'lí', '离为火', '离', '离'),
        '010011': ('丰', 'fēng', '雷火丰', '震', '离'),
        '010100': ('家人', 'jiā rén', '风火家人', '巽', '离'),
        '010101': ('既济', 'jì jì', '水火既济', '坎', '离'),
        '010110': ('贲', 'bì', '山火贲', '艮', '离'),
        '010111': ('明夷', 'míng yí', '地火明夷', '坤', '离'),
        '011000': ('无妄', 'wú wàng', '天雷无妄', '乾', '震'),
        '011001': ('随', 'suí', '泽雷随', '兑', '震'),
        '011010': ('噬嗑', 'shì kē', '火雷噬嗑', '离', '震'),
        '011011': ('震', 'zhèn', '震为雷', '震', '震'),
        '011100': ('益', 'yì', '风雷益', '巽', '震'),
        '011101': ('屯', 'tún', '水雷屯', '坎', '震'),
        '011110': ('颐', 'yí', '山雷颐', '艮', '震'),
        '011111': ('复', 'fù', '地雷复', '坤', '震'),
        '100000': ('姤', 'gòu', '天风姤', '乾', '巽'),
        '100001': ('大过', 'dà guò', '泽风大过', '兑', '巽'),
        '100010': ('鼎', 'dǐng', '火风鼎', '离', '巽'),
        '100011': ('恒', 'héng', '雷风恒', '震', '巽'),
        '100100': ('巽', 'xùn', '巽为风', '巽', '巽'),
        '100101': ('蛊', 'gǔ', '风水蛊', '坎', '巽'),
        '100110': ('升', 'shēng', '地风升', '坤', '巽'),
        '100111': ('讼', 'sòng', '天水讼', '乾', '坎'),
        '101000': ('遁', 'dùn', '天山遁', '艮', '乾'),
        '101001': ('咸', 'xián', '泽山咸', '兑', '艮'),
        '101010': ('旅', 'lǚ', '火山旅', '离', '艮'),
        '101011': ('小过', 'xiǎo guò', '雷山小过', '震', '艮'),
        '101100': ('渐', 'jiàn', '风山渐', '巽', '艮'),
        '101101': ('蹇', 'jiǎn', '水山蹇', '坎', '艮'),
        '101110': ('谦', 'qiān', '地山谦', '坤', '艮'),
        '101111': ('否', 'pǐ', '天地否', '坤', '乾'),
        '110000': ('萃', 'cuì', '泽地萃', '兑', '坤'),
        '110001': ('晋', 'jìn', '火地晋', '离', '坤'),
        '110010': ('坤', 'kūn', '坤为地', '坤', '坤'),
        '110011': ('豫', 'yù', '雷地豫', '震', '坤'),
        '110100': ('观', 'guān', '风地观', '巽', '坤'),
        '110101': ('比', 'bǐ', '水地比', '坎', '坤'),
        '110110': ('剥', 'bō', '山地剥', '艮', '坤'),
        '110111': ('师', 'shī', '地水师', '坤', '坎'),
        '111000': ('谦', 'qiān', '地山谦', '坤', '艮'),
        '111001': ('否', 'pǐ', '天地否', '乾', '坤'),
        '111010': ('讼', 'sòng', '天水讼', '坎', '乾'),
        '111011': ('困', 'kùn', '泽水困', '兑', '坎'),
        '111100': ('井', 'jǐng', '水风井', '坎', '巽'),
        '111101': ('坎', 'kǎn', '坎为水', '坎', '坎'),
        '111110': ('蒙', 'méng', '山水蒙', '艮', '坎'),
        '111111': ('师', 'shī', '地水师', '坤', '坎'),
    }
    
    # 正确完整的64卦映射
    COMPLETE_MAP = {
        '000000': ('乾', 'qián', '乾为天', '乾', '乾', '000', '000'),
        '000001': ('夬', 'guài', '泽天夬', '兑', '乾', '001', '000'),
        '000010': ('大有', 'dà yǒu', '火天大有', '离', '乾', '010', '000'),
        '000011': ('大壮', 'dà zhuàng', '雷天大壮', '震', '乾', '011', '000'),
        '000100': ('小畜', 'xiǎo chù', '风天小畜', '巽', '乾', '100', '000'),
        '000101': ('需', 'xū', '水天需', '坎', '乾', '101', '000'),
        '000110': ('大畜', 'dà chù', '山天大畜', '艮', '乾', '110', '000'),
        '000111': ('泰', 'tài', '地天泰', '坤', '乾', '111', '000'),
        '001000': ('履', 'lǚ', '天泽履', '乾', '兑', '000', '001'),
        '001001': ('兑', 'duì', '兑为泽', '兑', '兑', '001', '001'),
        '001010': ('睽', 'kuí', '火泽睽', '离', '兑', '010', '001'),
        '001011': ('归妹', 'guī mèi', '雷泽归妹', '震', '兑', '011', '001'),
        '001100': ('中孚', 'zhōng fú', '风泽中孚', '巽', '兑', '100', '001'),
        '001101': ('节', 'jié', '水泽节', '坎', '兑', '101', '001'),
        '001110': ('损', 'sǔn', '山泽损', '艮', '兑', '110', '001'),
        '001111': ('临', 'lín', '地泽临', '坤', '兑', '111', '001'),
        '010000': ('同人', 'tóng rén', '天火同人', '乾', '离', '000', '010'),
        '010001': ('革', 'gé', '泽火革', '兑', '离', '001', '010'),
        '010010': ('离', 'lí', '离为火', '离', '离', '010', '010'),
        '010011': ('丰', 'fēng', '雷火丰', '震', '离', '011', '010'),
        '010100': ('家人', 'jiā rén', '风火家人', '巽', '离', '100', '010'),
        '010101': ('既济', 'jì jì', '水火既济', '坎', '离', '101', '010'),
        '010110': ('贲', 'bì', '山火贲', '艮', '离', '110', '010'),
        '010111': ('明夷', 'míng yí', '地火明夷', '坤', '离', '111', '010'),
        '011000': ('无妄', 'wú wàng', '天雷无妄', '乾', '震', '000', '011'),
        '011001': ('随', 'suí', '泽雷随', '兑', '震', '001', '011'),
        '011010': ('噬嗑', 'shì kē', '火雷噬嗑', '离', '震', '010', '011'),
        '011011': ('震', 'zhèn', '震为雷', '震', '震', '011', '011'),
        '011100': ('益', 'yì', '风雷益', '巽', '震', '100', '011'),
        '011101': ('屯', 'tún', '水雷屯', '坎', '震', '101', '011'),
        '011110': ('颐', 'yí', '山雷颐', '艮', '震', '110', '011'),
        '011111': ('复', 'fù', '地雷复', '坤', '震', '111', '011'),
        '100000': ('姤', 'gòu', '天风姤', '乾', '巽', '000', '100'),
        '100001': ('大过', 'dà guò', '泽风大过', '兑', '巽', '001', '100'),
        '100010': ('鼎', 'dǐng', '火风鼎', '离', '巽', '010', '100'),
        '100011': ('恒', 'héng', '雷风恒', '震', '巽', '011', '100'),
        '100100': ('巽', 'xùn', '巽为风', '巽', '巽', '100', '100'),
        '100101': ('蛊', 'gǔ', '风水蛊', '坎', '巽', '101', '100'),
        '100110': ('升', 'shēng', '地风升', '坤', '巽', '111', '100'),
        '100111': ('讼', 'sòng', '天水讼', '乾', '坎', '000', '101'),
        '101000': ('遁', 'dùn', '天山遁', '艮', '乾', '110', '000'),
        '101001': ('咸', 'xián', '泽山咸', '兑', '艮', '001', '110'),
        '101010': ('旅', 'lǚ', '火山旅', '离', '艮', '010', '110'),
        '101011': ('小过', 'xiǎo guò', '雷山小过', '震', '艮', '011', '110'),
        '101100': ('渐', 'jiàn', '风山渐', '巽', '艮', '100', '110'),
        '101101': ('蹇', 'jiǎn', '水山蹇', '坎', '艮', '101', '110'),
        '101110': ('谦', 'qiān', '地山谦', '坤', '艮', '111', '110'),
        '101111': ('否', 'pǐ', '天地否', '坤', '乾', '111', '000'),
        '110000': ('萃', 'cuì', '泽地萃', '兑', '坤', '001', '111'),
        '110001': ('晋', 'jìn', '火地晋', '离', '坤', '010', '111'),
        '110010': ('坤', 'kūn', '坤为地', '坤', '坤', '111', '111'),
        '110011': ('豫', 'yù', '雷地豫', '震', '坤', '011', '111'),
        '110100': ('观', 'guān', '风地观', '巽', '坤', '100', '111'),
        '110101': ('比', 'bǐ', '水地比', '坎', '坤', '101', '111'),
        '110110': ('剥', 'bō', '山地剥', '艮', '坤', '110', '111'),
        '110111': ('师', 'shī', '地水师', '坤', '坎', '111', '101'),
        '111000': ('遁', 'dùn', '天山遁', '艮', '乾', '110', '000'),
        '111001': ('咸', 'xián', '泽山咸', '兑', '艮', '001', '110'),
        '111010': ('旅', 'lǚ', '火山旅', '离', '艮', '010', '110'),
        '111011': ('困', 'kùn', '泽水困', '兑', '坎', '001', '101'),
        '111100': ('井', 'jǐng', '水风井', '坎', '巽', '101', '100'),
        '111101': ('坎', 'kǎn', '坎为水', '坎', '坎', '101', '101'),
        '111110': ('蒙', 'méng', '山水蒙', '艮', '坎', '110', '101'),
        '111111': ('师', 'shī', '地水师', '坤', '坎', '111', '101'),
    }
    
    # 八卦名称映射
    TRIGRAM_NAMES = {
        '000': '乾', '001': '兑', '010': '离', '011': '震',
        '100': '巽', '101': '坎', '110': '艮', '111': '坤'
    }
    
    TRIGRAM_SYMBOLS = {
        '000': '☰', '001': '☱', '010': '☲', '011': '☳',
        '100': '☴', '101': '☵', '110': '☶', '111': '☷'
    }
    
    def __init__(self, data_path: str = None):
        self.hexagram_db = {}
        if data_path and os.path.exists(data_path):
            self._load_data(data_path)
    
    def _load_data(self, path: str) -> dict:
        with open(path, 'r', encoding='utf-8') as f:
            self.hexagram_db = json.load(f)
        return self.hexagram_db
    
    def milfoil(self, question: str = "", seed: Optional[str] = None) -> Hexagram:
        """大衍之数（蓍草法）"""
        if seed:
            random.seed(seed)
        
        yao_list = []
        changing = []
        
        for pos in range(1, 7):
            total = 49
            remainders = []
            for _ in range(3):
                left = random.randint(1, total - 1)
                right = total - left - 1
                left_r = left % 4 or 4
                right_r = right % 4 or 4
                change = left_r + right_r + 1
                remainders.append(change)
                total -= change
            
            final = 49 - sum(remainders)
            if final == 6:
                lt = LineType.OLD_YIN
                changing.append(pos)
            elif final == 7:
                lt = LineType.YOUNG_YANG
            elif final == 8:
                lt = LineType.YOUNG_YIN
            else:
                lt = LineType.OLD_YANG
                changing.append(pos)
            
            yao_list.append(Yao(pos, lt, lt in (LineType.OLD_YIN, LineType.OLD_YANG)))
        
        return self._build_hexagram(yao_list, changing, question, "大衍之数")
    
    def coin(self, question: str = "", seed: Optional[str] = None) -> Hexagram:
        """金钱卦"""
        if seed:
            random.seed(seed)
        
        yao_list = []
        changing = []
        
        for pos in range(1, 7):
            result = tuple(random.choice([0, 1]) for _ in range(3))
            count = sum(result)
            
            if count == 0:
                lt = LineType.OLD_YANG
                changing.append(pos)
            elif count == 1:
                lt = LineType.YOUNG_YANG
            elif count == 2:
                lt = LineType.YOUNG_YIN
            else:
                lt = LineType.OLD_YIN
                changing.append(pos)
            
            yao_list.append(Yao(pos, lt, lt in (LineType.OLD_YIN, LineType.OLD_YANG)))
        
        return self._build_hexagram(yao_list, changing, question, "金钱卦")
    
    def number(self, numbers: List[int], question: str = "") -> Hexagram:
        """数字卦"""
        if len(numbers) < 3:
            raise ValueError("数字卦需至少三个数字")
        
        upper = (numbers[0] % 8) or 8
        lower = (numbers[1] % 8) or 8
        change = (numbers[2] % 6) or 6
        
        trigram_map = {
            1: '000', 2: '001', 3: '010', 4: '011',
            5: '100', 6: '101', 7: '110', 8: '111'
        }
        
        full_code = trigram_map[lower] + trigram_map[upper]
        yao_list = []
        for i, bit in enumerate(full_code):
            val = int(bit)
            lt = LineType.YOUNG_YANG if val == 0 else LineType.YOUNG_YIN
            yao_list.append(Yao(i+1, lt, False))
        
        yao_list[change-1].line_type = (
            LineType.OLD_YANG if yao_list[change-1].value == 0 else LineType.OLD_YIN
        )
        yao_list[change-1].is_changing = True
        
        return self._build_hexagram(yao_list, [change], question, "数字卦")
    
    def _build_hexagram(self, yao_list, changing, question, method) -> Hexagram:
        binary = ''.join(str(y.value) for y in yao_list)
        
        # 优先从数据库查找
        hex_data = self.hexagram_db.get(binary, {})
        
        # 使用完整映射
        hex_info = self.COMPLETE_MAP.get(binary, None)
        
        if hex_data:
            name = hex_data.get("name", hex_info[0] if hex_info else "未知")
            chinese_name = hex_data.get("pinyin", hex_info[1] if hex_info else "")
            full_name = hex_data.get("full_name", hex_info[2] if hex_info else "")
            upper_name = hex_data.get("upper_trigram_name", hex_info[3] if hex_info else "未知")
            lower_name = hex_data.get("lower_trigram_name", hex_info[4] if hex_info else "未知")
            upper_code = hex_data.get("upper_trigram_code", hex_info[5] if hex_info else "000")
            lower_code = hex_data.get("lower_trigram_code", hex_info[6] if hex_info else "000")
        elif hex_info:
            name = hex_info[0]
            chinese_name = hex_info[1]
            full_name = hex_info[2]
            upper_name = hex_info[3]
            lower_name = hex_info[4]
            upper_code = hex_info[5]
            lower_code = hex_info[6]
        else:
            # Fallback
            lower_tri = ''.join(str(y.value) for y in yao_list[0:3])
            upper_tri = ''.join(str(y.value) for y in yao_list[3:6])
            return Hexagram(
                name="未知", chinese_name="wèi zhī",
                upper_trigram=self.TRIGRAM_NAMES.get(upper_tri, '未知'),
                lower_trigram=self.TRIGRAM_NAMES.get(lower_tri, '未知'),
                upper_trigram_code=upper_tri,
                lower_trigram_code=lower_tri,
                yao_list=yao_list, changing_yao=changing,
                question=question, method=method,
                timestamp=datetime.now().isoformat()
            )
        
        return Hexagram(
            name=name,
            chinese_name=chinese_name,
            upper_trigram=upper_name,
            lower_trigram=lower_name,
            upper_trigram_code=upper_code,
            lower_trigram_code=lower_code,
            yao_list=yao_list,
            changing_yao=changing,
            question=question,
            method=method,
            timestamp=datetime.now().isoformat()
        )
    
    def get_hexagram_info(self, binary_code: str) -> Optional[Dict]:
        """获取卦象详细信息"""
        return self.hexagram_db.get(binary_code, self.COMPLETE_MAP.get(binary_code))
    
    def get_changed_hexagram(self, hexagram: Hexagram) -> Optional[Hexagram]:
        """获取变卦"""
        if not hexagram.changing_yao:
            return None
        
        changed_yao_list = []
        for yao in hexagram.yao_list:
            new_type = LineType.YOUNG_YANG if yao.changed_value == 0 else LineType.YOUNG_YIN
            changed_yao_list.append(Yao(yao.position, new_type, False))
        
        return self._build_hexagram(changed_yao_list, [], hexagram.question, "变卦")
    
    def render(self, hexagram: Hexagram, show_details: bool = True) -> str:
        """渲染输出"""
        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"☯️ Cyber I Ching Master · {hexagram.method}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("善。吾已联网天地之气，为汝起卦。")
        lines.append("")
        
        if hexagram.question:
            lines.append(f"所问：{hexagram.question}")
            lines.append("")
        
        lines.append(hexagram.display())
        lines.append("")
        lines.append(f"得卦：{hexagram.upper_trigram}{hexagram.lower_trigram} {hexagram.name}（{hexagram.chinese_name}）")
        
        if hexagram.changing_yao:
            lines.append(f"变爻：第{', '.join(map(str, hexagram.changing_yao))}爻")
            
            # 显示变卦信息
            changed = self.get_changed_hexagram(hexagram)
            if changed:
                lines.append(f"之卦：{changed.upper_trigram}{changed.lower_trigram} {changed.name}（{changed.chinese_name}）")
        
        lines.append("")
        
        # 如果有详细信息，显示卦辞
        if show_details:
            hex_data = self.hexagram_db.get(hexagram.binary_code, {})
            if hex_data:
                if 'gua_ci' in hex_data:
                    lines.append(f"【卦辞】{hex_data['gua_ci']}")
                if 'xiang' in hex_data:
                    lines.append(f"【大象】{hex_data['xiang']}")
                if 'tuan' in hex_data:
                    lines.append(f"【彖传】{hex_data['tuan'][:100]}...")
        
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("卦象已存入底层逻辑，随时可供回溯。算法虽定，人为变量存疑，汝其慎之。")
        return '\n'.join(lines)


if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    import argparse
    parser = argparse.ArgumentParser(description='Cyber I Ching Master')
    parser.add_argument('--method', '-m', choices=['milfoil', 'coin', 'number'], default='coin')
    parser.add_argument('--question', '-q', default='')
    parser.add_argument('--seed', '-s', help='随机种子')
    parser.add_argument('--numbers', '-n', nargs='+', type=int)
    parser.add_argument('--data', '-d', default='', help='卦数据库路径')
    args = parser.parse_args()
    
    master = CyberIChingMaster(args.data if args.data else None)
    
    if args.method == 'milfoil':
        result = master.milfoil(args.question, args.seed)
    elif args.method == 'number':
        result = master.number(args.numbers or [123, 456, 789], args.question)
    else:
        result = master.coin(args.question, args.seed)
    
    print(master.render(result))
