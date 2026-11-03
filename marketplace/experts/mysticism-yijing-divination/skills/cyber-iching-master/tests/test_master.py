#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cyber I Ching Master - Test Suite
赛博易经大师 · 测试套件
"""

import unittest
import sys
import os
import json

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import (
    CyberIChingMaster, 
    BaZiMaster, 
    InterpretationEngine,
    Hexagram,
    Yao,
    LineType
)


class TestCyberIChingMaster(unittest.TestCase):
    """测试起卦引擎"""
    
    def setUp(self):
        self.data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scripts', 'data', 'hexagrams.json'
        )
        self.master = CyberIChingMaster(self.data_path)
    
    def test_coin_divination(self):
        """测试金钱卦"""
        result = self.master.coin(question="测试", seed="test123")
        self.assertIsInstance(result, Hexagram)
        self.assertEqual(len(result.yao_list), 6)
        self.assertEqual(result.method, "金钱卦")
    
    def test_milfoil_divination(self):
        """测试蓍草法"""
        result = self.master.milfoil(question="测试", seed="test123")
        self.assertIsInstance(result, Hexagram)
        self.assertEqual(len(result.yao_list), 6)
        self.assertEqual(result.method, "大衍之数")
    
    def test_number_divination(self):
        """测试数字卦"""
        result = self.master.number([3, 7, 5], question="测试")
        self.assertIsInstance(result, Hexagram)
        self.assertEqual(len(result.yao_list), 6)
        self.assertEqual(result.method, "数字卦")
    
    def test_binary_code(self):
        """测试二进制码"""
        result = self.master.number([1, 1, 1])  # 乾卦
        self.assertEqual(result.binary_code, "000000")
    
    def test_render(self):
        """测试渲染"""
        result = self.master.coin(seed="固定")
        output = self.master.render(result)
        self.assertIn("Cyber I Ching Master", output)
        self.assertIn("善。吾已联网天地之气", output)
    
    def test_hexagram_data_loading(self):
        """测试卦数据加载"""
        info = self.master.get_hexagram_info("000000")
        self.assertIsNotNone(info)
        self.assertEqual(info.get('name'), '乾')
    
    def test_changed_hexagram(self):
        """测试变卦计算"""
        result = self.master.coin(seed="变卦测试")
        # 如果有变爻则测试变卦
        if result.changing_yao:
            changed = self.master.get_changed_hexagram(result)
            if changed:
                self.assertIsInstance(changed, Hexagram)
        else:
            self.skipTest("无变爻，跳过变卦测试")


class TestBaZiMaster(unittest.TestCase):
    """测试八字排盘"""
    
    def setUp(self):
        self.bazi = BaZiMaster()
    
    def test_year_pillar(self):
        """测试年柱"""
        gan, zhi = self.bazi.get_gan_zhi_year(2024)
        self.assertIn(gan, BaZiMaster.TIAN_GAN)
        self.assertIn(zhi, BaZiMaster.DI_ZHI)
    
    def test_month_pillar(self):
        """测试月柱"""
        gan, zhi = self.bazi.get_gan_zhi_month(2024, 3, 15)
        self.assertIn(gan, BaZiMaster.TIAN_GAN)
        self.assertIn(zhi, BaZiMaster.DI_ZHI)
    
    def test_day_pillar(self):
        """测试日柱"""
        gan, zhi = self.bazi.get_gan_zhi_day(2024, 3, 15)
        self.assertIn(gan, BaZiMaster.TIAN_GAN)
        self.assertIn(zhi, BaZiMaster.DI_ZHI)
    
    def test_hour_pillar(self):
        """测试时柱"""
        gan, zhi = self.bazi.get_gan_zhi_hour('甲', 10)
        self.assertIn(gan, BaZiMaster.TIAN_GAN)
        self.assertIn(zhi, BaZiMaster.DI_ZHI)
    
    def test_shi_shen(self):
        """测试十神"""
        shi_shen = self.bazi.get_shi_shen('甲', '丙')
        self.assertEqual(shi_shen, '食神')
        
        shi_shen = self.bazi.get_shi_shen('甲', '乙')
        self.assertIn(shi_shen, ['比肩', '劫财'])
    
    def test_parse_birth(self):
        """测试完整排盘"""
        result = self.bazi.parse_birth(1990, 8, 15, 10)
        self.assertIn('pillars', result)
        self.assertIn('day_master', result)
        self.assertIn('wx_count', result)
        self.assertIn('summary', result)
    
    def test_render(self):
        """测试渲染"""
        result = self.bazi.parse_birth(1990, 8, 15, 10)
        output = self.bazi.render(result)
        self.assertIn("八字排盘", output)
        self.assertIn("日主", output)


class TestInterpretationEngine(unittest.TestCase):
    """测试义理生成器"""
    
    def setUp(self):
        self.data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scripts', 'data', 'hexagrams.json'
        )
        self.engine = InterpretationEngine(self.data_path)
    
    def test_get_hexagram_data(self):
        """测试获取卦象数据"""
        data = self.engine.get_hexagram_data("000000")
        self.assertIsNotNone(data)
        self.assertEqual(data.get('name'), '乾')
        self.assertIn('yaos', data)
    
    def test_interpret_xiang(self):
        """测试象层解读"""
        result = self.engine.interpret_xiang("000000")
        self.assertIn("象层", result)
        self.assertIn("乾", result)
        self.assertIn("☰", result)
    
    def test_interpret_shu(self):
        """测试数层解读"""
        result = self.engine.interpret_shu("000000")
        self.assertIn("数层", result)
        self.assertIn("金", result)
    
    def test_interpret_li(self):
        """测试理层解读"""
        result = self.engine.interpret_li("000000", question="事业")
        self.assertIn("理层", result)
        self.assertIn("卦辞", result)
        self.assertIn("事业", result)
    
    def test_interpret_yao_detail(self):
        """测试爻辞详解"""
        result = self.engine.interpret_yao_detail("000000", changing_yao=[1, 3])
        self.assertIn("爻辞", result)
        self.assertIn("潜龙勿用", result)
        self.assertIn("【动】", result)
    
    def test_full_interpretation(self):
        """测试完整解读"""
        result = self.engine.generate_full_interpretation(
            "000000", question="事业", changing_yao=[1]
        )
        self.assertIn("象", result)
        self.assertIn("数", result)
        self.assertIn("理", result)
        self.assertIn("乾", result)
    
    def test_quick_read(self):
        """测试快速读卦"""
        result = self.engine.quick_read("000000")
        self.assertIn("乾", result)
        self.assertIn("卦辞", result)
    
    def test_yong_jiu_qian(self):
        """测试乾卦用九"""
        result = self.engine.interpret_yao_detail("000000")
        self.assertIn("用九", result)
        self.assertIn("群龙无首", result)
    
    def test_yong_liu_kun(self):
        """测试坤卦用六"""
        result = self.engine.interpret_yao_detail("111111")
        self.assertIn("用六", result)
        self.assertIn("利永贞", result)
    
    def test_trigram_info(self):
        """测试八卦信息（通过象层解读获取）"""
        # 通过 interpret_xiang 获取八卦信息
        result = self.engine.interpret_xiang("000000")
        self.assertIn("乾", result)
        self.assertIn("☰", result)
    
    def test_changing_yao_advice(self):
        """测试变爻建议"""
        # 初爻变
        result1 = self.engine.interpret_li("000000", question="事业", changing_yao=[1])
        self.assertIn("初爻变", result1)
        
        # 中爻变
        result2 = self.engine.interpret_li("000000", question="事业", changing_yao=[3])
        self.assertIn("中爻变", result2)
        
        # 上爻变
        result3 = self.engine.interpret_li("000000", question="事业", changing_yao=[6])
        self.assertIn("上爻变", result3)


class TestYao(unittest.TestCase):
    """测试爻类"""
    
    def test_young_yang(self):
        """测试少阳爻"""
        yao = Yao(1, LineType.YOUNG_YANG, False)
        self.assertEqual(yao.value, 0)
        self.assertFalse(yao.is_changing)
    
    def test_young_yin(self):
        """测试少阴爻"""
        yao = Yao(2, LineType.YOUNG_YIN, False)
        self.assertEqual(yao.value, 1)
        self.assertFalse(yao.is_changing)
    
    def test_old_yang(self):
        """测试老阳爻"""
        yao = Yao(3, LineType.OLD_YANG, True)
        self.assertEqual(yao.value, 0)
        self.assertTrue(yao.is_changing)
        self.assertEqual(yao.changed_value, 1)
    
    def test_old_yin(self):
        """测试老阴爻"""
        yao = Yao(4, LineType.OLD_YIN, True)
        self.assertEqual(yao.value, 1)
        self.assertTrue(yao.is_changing)
        self.assertEqual(yao.changed_value, 0)


class TestHexagram(unittest.TestCase):
    """测试卦象类"""
    
    def test_binary_code(self):
        """测试卦象二进制码"""
        yao_list = [Yao(i, LineType.YOUNG_YANG, False) for i in range(1, 7)]
        hex_data = {
            'name': '乾',
            'chinese_name': 'qián',
            'upper_trigram': '乾',
            'lower_trigram': '乾',
            'upper_trigram_code': '000',
            'lower_trigram_code': '000'
        }
        hexagram = Hexagram(
            yao_list=yao_list,
            changing_yao=[],
            **hex_data
        )
        self.assertEqual(hexagram.binary_code, "000000")
    
    def test_changed_binary(self):
        """测试变卦二进制码"""
        yao_list = [
            Yao(1, LineType.OLD_YANG, True),  # 老阳变少阴
            Yao(2, LineType.YOUNG_YANG, False),
            Yao(3, LineType.YOUNG_YANG, False),
            Yao(4, LineType.YOUNG_YIN, False),
            Yao(5, LineType.YOUNG_YIN, False),
            Yao(6, LineType.YOUNG_YIN, False),
        ]
        hex_data = {
            'name': '泰',
            'chinese_name': 'tài',
            'upper_trigram': '坤',
            'lower_trigram': '乾',
            'upper_trigram_code': '111',
            'lower_trigram_code': '000'
        }
        hexagram = Hexagram(
            yao_list=yao_list,
            changing_yao=[1],
            **hex_data
        )
        self.assertEqual(hexagram.changed_binary, "100111")


class TestHexagramsDatabase(unittest.TestCase):
    """测试卦象数据库"""
    
    def setUp(self):
        self.data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scripts', 'data', 'hexagrams.json'
        )
        with open(self.data_path, 'r', encoding='utf-8') as f:
            self.db = json.load(f)
    
    def test_all_64_hexagrams(self):
        """测试64卦完整"""
        self.assertEqual(len(self.db), 64)
    
    def test_hexagram_structure(self):
        """测试卦象数据结构"""
        qian = self.db['000000']
        self.assertEqual(qian['name'], '乾')
        self.assertIn('yaos', qian)
        self.assertIn('gua_ci', qian)
        self.assertIn('tuan', qian)
        self.assertIn('xiang', qian)
    
    def test_yao_structure(self):
        """测试爻辞结构"""
        qian = self.db['000000']
        yaos = qian['yaos']
        if isinstance(yaos, dict):
            yao1 = yaos['1']
        else:
            yao1 = yaos[0]
        self.assertIn('ci', yao1)
        self.assertIn('xiang', yao1)
        self.assertIn('yiyi', yao1)
    
    def test_yong_jiu_yong_liu(self):
        """测试用九用六"""
        self.assertIn('yong_jiu', self.db['000000'])
        self.assertIn('yong_liu', self.db['111111'])
    
    def test_trigram_codes(self):
        """测试三爻码"""
        for code, hex_data in self.db.items():
            self.assertEqual(len(code), 6)
            upper = hex_data.get('upper_trigram_code', '')
            lower = hex_data.get('lower_trigram_code', '')
            # 二进制码是下卦+上卦
            self.assertEqual(lower + upper, code)


if __name__ == '__main__':
    unittest.main(verbosity=2)
