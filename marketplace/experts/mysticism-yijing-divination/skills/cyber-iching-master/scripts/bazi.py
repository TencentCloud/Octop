#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cyber I Ching Master — BaZi Module
赛博易经大师 · 八字排盘模块
"""

from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Optional


class BaZiMaster:
    """八字排盘与命局分析"""
    
    # 天干
    TIAN_GAN = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
    # 地支
    DI_ZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
    
    # 天干五行
    TG_WUXING = {
        '甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
        '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'
    }
    
    # 地支五行
    DZ_WUXING = {
        '子': '水', '丑': '土', '寅': '木', '卯': '木', '辰': '土',
        '巳': '火', '午': '火', '未': '土', '申': '金', '酉': '金',
        '戌': '土', '亥': '水'
    }
    
    # 地支藏干
    DZ_CANG_GAN = {
        '子': ['癸'], '丑': ['己', '癸', '辛'], '寅': ['甲', '丙', '戊'],
        '卯': ['乙'], '辰': ['戊', '乙', '癸'], '巳': ['丙', '庚', '戊'],
        '午': ['丁', '己'], '未': ['己', '丁', '乙'], '申': ['庚', '壬', '戊'],
        '酉': ['辛'], '戌': ['戊', '辛', '丁'], '亥': ['壬', '甲']
    }
    
    # 纳音五行（完整60甲子）
    NAYIN = {
        ('甲', '子'): '海中金', ('乙', '丑'): '海中金',
        ('丙', '寅'): '炉中火', ('丁', '卯'): '炉中火',
        ('戊', '辰'): '大林木', ('己', '巳'): '大林木',
        ('庚', '午'): '路旁土', ('辛', '未'): '路旁土',
        ('壬', '申'): '剑锋金', ('癸', '酉'): '剑锋金',
        ('甲', '戌'): '山头火', ('乙', '亥'): '山头火',
        ('丙', '子'): '涧下水', ('丁', '丑'): '涧下水',
        ('戊', '寅'): '城头土', ('己', '卯'): '城头土',
        ('庚', '辰'): '白蜡金', ('辛', '巳'): '白蜡金',
        ('壬', '午'): '杨柳木', ('癸', '未'): '杨柳木',
        ('甲', '申'): '泉中水', ('乙', '酉'): '泉中水',
        ('丙', '戌'): '屋上土', ('丁', '亥'): '屋上土',
        ('戊', '子'): '霹雳火', ('己', '丑'): '霹雳火',
        ('庚', '寅'): '松柏木', ('辛', '卯'): '松柏木',
        ('壬', '辰'): '长流水', ('癸', '巳'): '长流水',
        ('甲', '午'): '沙中金', ('乙', '未'): '沙中金',
        ('丙', '申'): '山下火', ('丁', '酉'): '山下火',
        ('戊', '戌'): '平地木', ('己', '亥'): '平地木',
        ('庚', '子'): '壁上土', ('辛', '丑'): '壁上土',
        ('壬', '寅'): '金箔金', ('癸', '卯'): '金箔金',
        ('甲', '辰'): '覆灯火', ('乙', '巳'): '覆灯火',
        ('丙', '午'): '天河水', ('丁', '未'): '天河水',
        ('戊', '申'): '大驿土', ('己', '酉'): '大驿土',
        ('庚', '戌'): '钗钏金', ('辛', '亥'): '钗钏金',
        ('壬', '子'): '桑柘木', ('癸', '丑'): '桑柘木',
        ('甲', '寅'): '大溪水', ('乙', '卯'): '大溪水',
        ('丙', '辰'): '沙中土', ('丁', '巳'): '沙中土',
        ('戊', '午'): '天上火', ('己', '未'): '天上火',
        ('庚', '申'): '石榴木', ('辛', '酉'): '石榴木',
        ('壬', '戌'): '大海水', ('癸', '亥'): '大海水',
    }
    
    # 月支索引（正月建寅）
    MONTH_ZHI_INDEX = {
        1: 2,   # 正月寅
        2: 3,   # 二月卯
        3: 4,   # 三月辰
        4: 5,   # 四月巳
        5: 6,   # 五月午
        6: 7,   # 六月未
        7: 8,   # 七月申
        8: 9,   # 八月酉
        9: 10,  # 九月戌
        10: 11, # 十月亥
        11: 0,  # 十一月子
        12: 1,  # 十二月丑
    }
    
    def __init__(self):
        pass
    
    def get_gan_zhi_year(self, year: int) -> Tuple[str, str]:
        """计算年柱干支"""
        gan = self.TIAN_GAN[(year - 4) % 10]
        zhi = self.DI_ZHI[(year - 4) % 12]
        return gan, zhi
    
    def get_gan_zhi_month(self, year: int, month: int, day: int) -> Tuple[str, str]:
        """计算月柱干支（基于节气，简化版）"""
        year_gan, _ = self.get_gan_zhi_year(year)
        
        # 月干根据年干确定（五虎遁）
        month_gan_start = {
            '甲': '丙', '己': '丙',
            '乙': '戊', '庚': '戊',
            '丙': '庚', '辛': '庚',
            '丁': '壬', '壬': '壬',
            '戊': '甲', '癸': '甲'
        }
        start_gan_idx = self.TIAN_GAN.index(month_gan_start[year_gan])
        
        # 月支：正月建寅
        zhi_idx = self.MONTH_ZHI_INDEX.get(month, 2)
        zhi = self.DI_ZHI[zhi_idx]
        
        gan_idx = (start_gan_idx + month - 1) % 10
        return self.TIAN_GAN[gan_idx], zhi
    
    def get_gan_zhi_day(self, year: int, month: int, day: int) -> Tuple[str, str]:
        """计算日柱干支（基于公历日期）"""
        # 使用已知基准日推算：1900-01-31 为甲辰日
        base_date = datetime(1900, 1, 31)
        target_date = datetime(year, month, day)
        delta = (target_date - base_date).days
        
        gan = self.TIAN_GAN[(delta + 0) % 10]  # 甲=0
        zhi = self.DI_ZHI[(delta + 4) % 12]    # 辰=4
        return gan, zhi
    
    def get_gan_zhi_hour(self, day_gan: str, hour: int) -> Tuple[str, str]:
        """计算时柱干支"""
        # 时辰地支：子时23-1点，丑时1-3点...
        if hour >= 23 or hour < 1:
            zhi = '子'
        else:
            zhi_idx = ((hour + 1) // 2) % 12
            zhi = self.DI_ZHI[zhi_idx]
        
        # 时干根据日干（五鼠遁）
        hour_gan_start = {
            '甲': '甲', '己': '甲',
            '乙': '丙', '庚': '丙',
            '丙': '戊', '辛': '戊',
            '丁': '庚', '壬': '庚',
            '戊': '壬', '癸': '壬'
        }
        start_gan_idx = self.TIAN_GAN.index(hour_gan_start[day_gan])
        
        # 子时为第一个
        zhi_order = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
        zhi_idx = zhi_order.index(zhi)
        gan_idx = (start_gan_idx + zhi_idx) % 10
        
        return self.TIAN_GAN[gan_idx], zhi
    
    def get_shi_shen(self, day_gan: str, target_gan: str) -> str:
        """计算十神"""
        # 五行生克关系
        sheng = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
        ke = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}
        
        day_wx = self.TG_WUXING[day_gan]
        target_wx = self.TG_WUXING[target_gan]
        
        # 同我/异我（阴阳）
        day_idx = self.TIAN_GAN.index(day_gan)
        target_idx = self.TIAN_GAN.index(target_gan)
        same_yin_yang = (day_idx % 2) == (target_idx % 2)
        
        if target_wx == day_wx:
            return '比肩' if same_yin_yang else '劫财'
        elif sheng[day_wx] == target_wx:
            return '食神' if same_yin_yang else '伤官'
        elif sheng[target_wx] == day_wx:
            return '偏财' if same_yin_yang else '正财'
        elif ke[day_wx] == target_wx:
            return '七杀' if same_yin_yang else '正官'
        elif ke[target_wx] == day_wx:
            return '偏印' if same_yin_yang else '正印'
        
        return '未知'
    
    def get_nayin(self, gan: str, zhi: str) -> str:
        """查纳音"""
        return self.NAYIN.get((gan, zhi), '未知')
    
    def parse_birth(self, year: int, month: int, day: int, hour: int) -> Dict:
        """
        完整排盘
        
        Args:
            year, month, day: 公历日期
            hour: 0-23
        
        Returns:
            Dict: 完整八字信息
        """
        # 四柱
        year_gz = self.get_gan_zhi_year(year)
        month_gz = self.get_gan_zhi_month(year, month, day)
        day_gz = self.get_gan_zhi_day(year, month, day)
        hour_gz = self.get_gan_zhi_hour(day_gz[0], hour)
        
        pillars = {
            'year':  {'gan': year_gz[0], 'zhi': year_gz[1], 'nayin': self.get_nayin(*year_gz)},
            'month': {'gan': month_gz[0], 'zhi': month_gz[1], 'nayin': self.get_nayin(*month_gz)},
            'day':   {'gan': day_gz[0], 'zhi': day_gz[1], 'nayin': self.get_nayin(*day_gz)},
            'hour':  {'gan': hour_gz[0], 'zhi': hour_gz[1], 'nayin': self.get_nayin(*hour_gz)},
        }
        
        # 日主
        day_master = day_gz[0]
        day_master_wx = self.TG_WUXING[day_master]
        
        # 十神分析
        for pillar_name, pillar in pillars.items():
            if pillar_name == 'day':
                pillar['shi_shen'] = '日主'
            else:
                pillar['shi_shen'] = self.get_shi_shen(day_master, pillar['gan'])
        
        # 地支藏干及十神
        for pillar_name, pillar in pillars.items():
            cang_gan = self.DZ_CANG_GAN[pillar['zhi']]
            pillar['cang_gan'] = [
                {'gan': g, 'shi_shen': self.get_shi_shen(day_master, g)}
                for g in cang_gan
            ]
        
        # 五行统计
        wx_count = {'金': 0, '木': 0, '水': 0, '火': 0, '土': 0}
        # 天干
        for p in pillars.values():
            wx_count[self.TG_WUXING[p['gan']]] += 1
        # 地支本气
        for p in pillars.values():
            wx_count[self.DZ_WUXING[p['zhi']]] += 1
        
        # 判断旺衰（简化版）
        wx_status = self._judge_wang_shuai(day_master_wx, wx_count, month_gz[1])
        
        return {
            'birth_date': f'{year}年{month}月{day}日{hour}时',
            'pillars': pillars,
            'day_master': day_master,
            'day_master_wx': day_master_wx,
            'wx_count': wx_count,
            'wx_status': wx_status,
            'nayin_year': pillars['year']['nayin'],
            'summary': self._generate_summary(pillars, day_master, wx_count, wx_status)
        }
    
    def _judge_wang_shuai(self, day_master_wx: str, wx_count: Dict, month_zhi: str) -> str:
        """判断日主旺衰（简化版）"""
        month_wx = self.DZ_WUXING[month_zhi]
        
        # 得令
        de_ling = False
        if day_master_wx == month_wx:
            de_ling = True
        # 木旺于春（寅卯），火旺于夏（巳午），金旺于秋（申酉），水旺于冬（亥子）
        wang_map = {
            '木': ['寅', '卯'],
            '火': ['巳', '午'],
            '金': ['申', '酉'],
            '水': ['亥', '子'],
            '土': ['辰', '戌', '丑', '未']
        }
        if month_zhi in wang_map.get(day_master_wx, []):
            de_ling = True
        
        # 得地（地支有根）
        de_di = wx_count[day_master_wx] >= 2
        
        # 得势（同党多）
        tong_dang = 0
        if day_master_wx in ['木', '水']:
            tong_dang = wx_count['木'] + wx_count['水']
        elif day_master_wx in ['火', '土']:
            tong_dang = wx_count['火'] + wx_count['土']
        elif day_master_wx in ['金']:
            tong_dang = wx_count['金'] + wx_count['土']
        elif day_master_wx in ['水']:
            tong_dang = wx_count['水'] + wx_count['金']
        
        de_shi = tong_dang >= 4
        
        if de_ling and (de_di or de_shi):
            return "身旺"
        elif de_ling:
            return "中和偏旺"
        elif de_di or de_shi:
            return "中和偏弱"
        else:
            return "身弱"
    
    def _generate_summary(self, pillars: Dict, day_master: str, 
                          wx_count: Dict, wx_status: str) -> str:
        """生成命局简评"""
        parts = []
        
        # 日主性格
        day_master_wx = self.TG_WUXING[day_master]
        wx_personality = {
            '木': "仁慈正直，有上进心，但有时固执。",
            '火': "热情礼貌，急躁冲动，富有表现力。",
            '土': "诚实守信，稳重踏实，但有时保守。",
            '金': "刚毅果断，讲义气，但有时冷酷。",
            '水': "聪明灵活，善变通，但有时多疑。"
        }
        
        parts.append(f"日主为{day_master}（{day_master_wx}）。{wx_personality.get(day_master_wx, '')}")
        parts.append(f"五行分布：金{wx_count['金']} 木{wx_count['木']} 水{wx_count['水']} 火{wx_count['火']} 土{wx_count['土']}。")
        parts.append(f"日主{wx_status}。")
        
        # 十神格局
        shi_shen_list = [p['shi_shen'] for p in pillars.values() if p['shi_shen'] != '日主']
        if '正印' in shi_shen_list or '偏印' in shi_shen_list:
            parts.append("印星透干，主聪慧多思，利学术技艺。")
        if '食神' in shi_shen_list or '伤官' in shi_shen_list:
            parts.append("食伤泄秀，主表达力强，宜创意技术。")
        if '正官' in shi_shen_list or '七杀' in shi_shen_list:
            parts.append("官杀有制，主有管理才能，宜仕途事业。")
        if '正财' in shi_shen_list or '偏财' in shi_shen_list:
            parts.append("财星有力，主理财有方，宜经商投资。")
        
        return '\n'.join(parts)
    
    def render(self, result: Dict) -> str:
        """渲染八字排盘"""
        p = result['pillars']
        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("☯️ Cyber I Ching Master · 八字排盘")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(f"出生时间：{result['birth_date']}")
        lines.append("")
        lines.append(f"{'柱':<4} {'天干':<6} {'地支':<6} {'藏干':<20} {'十神':<6} {'纳音':<8}")
        lines.append("-" * 60)
        
        for name, label in [('year', '年柱'), ('month', '月柱'), ('day', '日柱'), ('hour', '时柱')]:
            pillar = p[name]
            cang = ' '.join([f"{c['gan']}({c['shi_shen']})" for c in pillar['cang_gan']])
            lines.append(f"{label:<4} {pillar['gan']:<6} {pillar['zhi']:<6} {cang:<20} {pillar['shi_shen']:<6} {pillar['nayin']:<8}")
        
        lines.append("")
        lines.append(f"日主：{result['day_master']}（{result['day_master_wx']}）")
        lines.append(f"五行：金{result['wx_count']['金']} 木{result['wx_count']['木']} 水{result['wx_count']['水']} 火{result['wx_count']['火']} 土{result['wx_count']['土']}")
        lines.append(f"旺衰：{result['wx_status']}")
        lines.append(f"年命纳音：{result['nayin_year']}")
        lines.append("")
        lines.append("【命局简评】")
        lines.append(result['summary'])
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        return '\n'.join(lines)


# ============ CLI ============
if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    import argparse
    
    parser = argparse.ArgumentParser(description='BaZi Master')
    parser.add_argument('--year', '-y', type=int, required=True)
    parser.add_argument('--month', '-m', type=int, required=True)
    parser.add_argument('--day', '-d', type=int, required=True)
    parser.add_argument('--hour', '-hh', type=int, required=True, help='0-23')
    
    args = parser.parse_args()
    
    master = BaZiMaster()
    result = master.parse_birth(args.year, args.month, args.day, args.hour)
    print(master.render(result))
