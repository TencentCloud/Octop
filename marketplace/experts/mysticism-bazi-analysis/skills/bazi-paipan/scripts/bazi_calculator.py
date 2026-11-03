#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
八字排盘计算器 v2.0
==============
使用天文算法精确计算八字排盘
- 真太阳时修正（经度时差 + 均时差）
- 节气精确计算（VSOP87简化算法，精度 ±1分钟）
- 四柱推算（年柱、月柱、日柱、时柱）含藏干、十神、长生、空亡、纳音
- 刑冲合害分析
- 神煞分析（四柱神煞、大运神煞、流年神煞）
- 大运推算（起运年龄、顺逆大运）

作者: 六十八公斤
日期: 2026-03-25
升级: v2.0 - 新增藏干/十神/长生/刑冲合害/神煞等完整分析
"""

import sys
import io
import math
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Set

# 强制 stdout/stderr 使用 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 确保脚本所在目录在 Python 路径中（修复调试器找不到模块的问题）
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# 导入数据表
try:
    from bazi_data import (
        CANGGAN, SHISHEN_TIANGAN, SHISHEN_DIZHI_BASE, CHANGSHENG,
        KONGWANG, NAYIN_DICT, TIANGAN_HE, DIZHI_LIUHE, DIZHI_SANHE,
        DIZHI_ANHE, DIZHI_SANXING, DIZHI_ZIXING, DIZHI_LIUCHONG,
        DIZHI_LIUHAI, DIZHI_PO, DIZHI_SANHUI, ZIZUO,
        NIAN_SHENSHA, YUE_SHENSHA, RI_SHENSHA, SHI_SHENSHA,
        DAYUN_SHENSHA, LIUNIAN_SHENSHA
    )
except ImportError:
    print("[错误] 未找到 bazi_data.py，请确保数据表文件在同一目录")
    sys.exit(1)


# ============================================================
# 基础数据表
# ============================================================

TIANGAN = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
DIZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
WUXING_TIAN = ['木', '木', '火', '火', '土', '土', '金', '金', '水', '水']
WUXING_DI   = ['水', '土', '木', '木', '土', '火', '火', '土', '金', '金', '土', '水']
YINYANG_TIAN = ['阳', '阴', '阳', '阴', '阳', '阴', '阳', '阴', '阳', '阴']

# 节气与太阳黄经映射
SOLAR_TERMS_MAP = [
    ('小寒',  285), ('大寒',  300), ('立春',  315), ('雨水',  330),
    ('惊蛰',  345), ('春分',    0), ('清明',   15), ('谷雨',   30),
    ('立夏',   45), ('小满',   60), ('芒种',   75), ('夏至',   90),
    ('小暑',  105), ('大暑',  120), ('立秋',  135), ('处暑',  150),
    ('白露',  165), ('秋分',  180), ('寒露',  195), ('霜降',  210),
    ('立冬',  225), ('小雪',  240), ('大雪',  255), ('冬至',  270),
]

MONTH_START_TERMS = [
    '立春', '惊蛰', '清明', '立夏', '芒种', '小暑',
    '立秋', '寒露', '立冬', '大雪', '小寒', '大寒',
]

# 城市数据库（保持原版完整）
CITY_DATABASE = {
    '阿坝藏族羌族自治州': (102.2286, 31.9058),
    '阿克苏地区': (80.2698, 41.1717),
    '阿拉善盟': (105.6957, 38.8431),
    '阿里地区': (81.1077, 30.4046),
    '安康市': (109.038, 32.7044),
    '安庆市': (117.0587, 30.5379),
    '鞍山市': (123.0078, 41.1187),
    '安顺市': (105.9283, 26.2286),
    '安阳市': (114.3518, 36.1103),
    '澳门': (113.5497, 22.193),
    '白城市': (122.8408, 45.6211),
    '百色市': (106.6318, 23.9015),
    '白山市': (126.4358, 41.9459),
    '白银市': (104.1712, 36.5467),
    '保定市': (115.4948, 38.8866),
    '宝鸡市': (107.1706, 34.3641),
    '保山市': (99.178, 25.1205),
    '包头市': (109.8462, 40.6471),
    '巴彦淖尔市': (107.4238, 40.7692),
    '巴音郭楞蒙古自治州': (86.1217, 41.7714),
    '巴中市': (106.7579, 31.8692),
    '北海市': (109.1226, 21.4727),
    '北京市': (116.3956, 39.93),
    '蚌埠市': (117.3571, 32.9295),
    '本溪市': (123.7781, 41.3258),
    '毕节市': (105.3333, 27.4086),
    '滨州市': (117.9683, 37.4053),
    '博尔塔拉蒙古自治州': (82.0524, 44.9137),
    '亳州市': (115.7879, 33.8712),
    '沧州市': (116.8638, 38.2976),
    '长春市': (125.3136, 43.8983),
    '常德市': (111.6537, 29.0121),
    '昌都市': (97.1856, 31.1406),
    '昌吉回族自治州': (87.296, 44.0071),
    '长沙市': (112.9794, 28.2135),
    '常熟市': (94.662, 40.1421),
    '长治市': (113.1203, 36.2017),
    '常州市': (119.9819, 31.7714),
    '潮州市': (116.6301, 23.6618),
    '承德市': (117.9338, 40.9925),
    '成都市': (104.0679, 30.6799),
    '郴州市': (113.0377, 25.7823),
    '赤峰市': (118.9308, 42.2971),
    '池州市': (117.4945, 33.66),
    '重庆市': (106.5306, 29.5446),
    '崇左市': (107.3573, 22.4155),
    '楚雄彝族自治州': (101.5294, 25.0664),
    '滁州市': (118.3246, 32.3174),
    '大连市': (121.5935, 38.9487),
    '大理白族自治州': (100.2237, 25.5969),
    '丹东市': (124.3385, 40.129),
    '大庆市': (125.0218, 46.5967),
    '大同市': (113.2905, 40.1137),
    '大兴安岭地区': (124.1961, 51.9918),
    '达州市': (107.495, 31.2142),
    '德宏傣族景颇族自治州': (98.5894, 24.4412),
    '德阳市': (104.4024, 31.1311),
    '德州市': (116.3282, 37.4608),
    '定西市': (104.6266, 35.5861),
    '迪庆藏族自治州': (99.7137, 27.831),
    '东莞市': (113.7634, 23.043),
    '东营市': (118.5839, 37.4871),
    '敦煌': (120.7525, 31.6544),
    '鄂尔多斯市': (109.9937, 39.8165),
    '恩施土家族苗族自治州': (109.4919, 30.2859),
    '鄂州市': (114.8956, 30.3844),
    '防城港市': (108.3518, 21.6174),
    '佛山市': (113.134, 23.0351),
    '福鼎市': (120.217, 27.3245),
    '抚顺市': (123.9298, 41.8773),
    '阜新市': (121.6608, 42.0193),
    '阜阳市': (115.8209, 32.9012),
    '福州市': (119.3302, 26.0471),
    '甘南藏族自治州': (102.9174, 34.9922),
    '赣州市': (114.9359, 25.8453),
    '甘孜藏族自治州': (101.9692, 30.0551),
    '高雄市': (120.3014, 22.6273),
    '高邮市': (119.4592, 32.7817),
    '公主岭': (124.6859, 43.7918),
    '广安市': (106.6357, 30.464),
    '广元市': (105.8197, 32.441),
    '广州市': (113.3076, 23.12),
    '贵港市': (109.6137, 23.1034),
    '桂林市': (110.2609, 25.2629),
    '贵阳市': (106.7092, 26.6299),
    '果洛藏族自治州': (100.2237, 34.4805),
    '固原市': (106.2853, 36.0215),
    '哈尔滨市': (126.6577, 45.7732),
    '海北藏族自治州': (100.8798, 36.9607),
    '海东市': (102.0852, 36.5176),
    '海口市': (110.3308, 20.0221),
    '海南藏族自治州': (100.6241, 36.2844),
    '海西蒙古族藏族自治州': (97.3426, 37.3738),
    '哈密市': (93.5294, 42.3445),
    '邯郸市': (114.4827, 36.6093),
    '杭州市': (120.2194, 30.2592),
    '汉中市': (107.0455, 33.0816),
    '鹤壁市': (114.2978, 35.7554),
    '河池市': (108.0699, 24.6995),
    '合肥市': (117.2827, 31.8669),
    '鹤岗市': (130.2925, 47.3387),
    '黑河市': (127.5008, 50.2507),
    '衡水市': (115.6862, 37.7469),
    '衡阳市': (112.5838, 26.8982),
    '和田地区': (79.9302, 37.1168),
    '河源市': (114.7137, 23.7573),
    '菏泽市': (115.4634, 35.2624),
    '贺州市': (111.5526, 24.4111),
    '呼和浩特市': (111.6604, 40.8283),
    '红河哈尼族彝族自治州': (103.3841, 23.3677),
    '香港': (114.1861, 22.2936),
    '淮安市': (119.0302, 33.6065),
    '淮北市': (116.7914, 33.96),
    '怀化市': (109.987, 27.5575),
    '淮南市': (117.0186, 32.6428),
    '黄冈市': (114.9066, 30.4461),
    '黄南藏族自治州': (102.0076, 35.5229),
    '黄山市': (118.2936, 29.7344),
    '黄石市': (115.0507, 30.2161),
    '惠州市': (114.4107, 23.1135),
    '葫芦岛市': (120.8608, 40.743),
    '呼伦贝尔市': (119.7608, 49.2016),
    '湖州市': (120.1372, 30.8779),
    '佳木斯市': (130.2847, 46.8138),
    '吉安市': (114.992, 27.1138),
    '江门市': (113.0781, 22.5751),
    '简阳市': (104.5472, 30.4113),
    '焦作市': (113.2118, 35.2346),
    '嘉兴市': (120.7604, 30.774),
    '嘉峪关市': (98.2816, 39.8024),
    '揭阳市': (116.3795, 23.548),
    '吉林市': (126.5645, 43.872),
    '吉林省长白山保护开发区': (128.139, 42.456),
    '济南市': (117.025, 36.6828),
    '金昌市': (102.2081, 38.5161),
    '晋城市': (112.8673, 35.4998),
    '景德镇市': (117.1865, 29.3036),
    '荆门市': (112.2173, 31.0426),
    '荆州市': (112.2419, 30.3326),
    '金华市': (119.6526, 29.1029),
    '济宁市': (116.6008, 35.4021),
    '晋中市': (112.7385, 37.6934),
    '锦州市': (121.1477, 41.1309),
    '九江市': (115.9998, 29.7196),
    '酒泉市': (98.5084, 39.7415),
    '鸡西市': (130.9418, 45.3215),
    '济源市': (112.4053, 35.1054),
    '开封市': (114.3516, 34.8019),
    '克拉玛依市': (84.8812, 45.5943),
    '喀什地区': (75.993, 39.4706),
    '克孜勒苏柯尔克孜自治州': (76.1376, 39.7503),
    '昆明市': (102.7146, 25.0492),
    '昆山市': (120.9807, 31.3856),
    '来宾市': (109.2318, 23.7412),
    '莱芜市': (117.6847, 36.2337),
    '廊坊市': (116.7036, 39.5186),
    '兰州市': (103.8233, 36.0642),
    '拉萨市': (91.1119, 29.6626),
    '乐山市': (103.7608, 29.601),
    '凉山彝族自治州': (102.2596, 27.8924),
    '连云港市': (119.1739, 34.6015),
    '聊城市': (115.9869, 36.4558),
    '辽阳市': (123.1725, 41.2733),
    '辽源市': (125.1337, 42.9233),
    '丽江市': (100.2296, 26.8754),
    '临沧市': (100.0926, 23.8878),
    '临汾市': (111.5388, 36.0997),
    '临夏回族自治州': (103.2152, 35.5985),
    '临沂市': (118.3408, 35.0724),
    '林芝市': (94.35, 29.6669),
    '丽水市': (119.9296, 28.4563),
    '六盘水市': (104.8521, 26.5919),
    '柳州市': (109.4224, 24.3291),
    '陇南市': (104.9346, 33.3945),
    '龙岩市': (117.018, 25.0787),
    '娄底市': (111.9964, 27.7411),
    '六安市': (116.5053, 31.7556),
    '漯河市': (114.0461, 33.5763),
    '洛阳市': (112.4475, 34.6574),
    '泸州市': (105.444, 28.8959),
    '吕梁市': (111.1432, 37.5273),
    '马鞍山市': (118.5159, 31.6885),
    '茂名市': (110.9312, 21.6682),
    '梅河口': (125.7235, 42.5426),
    '眉山市': (103.8414, 30.0611),
    '梅州市': (116.1264, 24.3046),
    '绵阳市': (104.7055, 31.5047),
    '牡丹江市': (129.608, 44.5885),
    '南昌市': (115.8935, 28.6896),
    '南充市': (106.1056, 30.801),
    '南京市': (118.7781, 32.0572),
    '南宁市': (108.2972, 22.8065),
    '南平市': (118.1819, 26.6436),
    '南通市': (120.8738, 32.0147),
    '南阳市': (112.5428, 33.0114),
    '那曲地区': (92.067, 31.4807),
    '内江市': (105.0731, 29.5995),
    '新北市': (121.577, 25.0287),
    '宁波市': (121.579, 29.8853),
    '宁德市': (119.5421, 26.6565),
    '怒江傈僳族自治州': (98.8599, 25.8607),
    '盘锦市': (122.0732, 41.1412),
    '攀枝花市': (101.7224, 26.5876),
    '平顶山市': (113.3008, 33.7453),
    '平凉市': (106.6889, 35.5501),
    '平潭市': (119.7665, 25.5377),
    '萍乡市': (113.8599, 27.6395),
    '普洱市': (100.9801, 22.7888),
    '莆田市': (119.0777, 25.4485),
    '濮阳市': (115.0266, 35.7533),
    '黔东南苗族侗族自治州': (107.9854, 26.584),
    '潜江市': (112.7688, 30.3431),
    '黔南布依族苗族自治州': (107.5232, 26.2645),
    '黔西南布依族苗族自治州': (104.9006, 25.0951),
    '青岛市': (120.3844, 36.1052),
    '庆阳市': (107.6442, 35.7268),
    '清远市': (113.0408, 23.6985),
    '秦皇岛市': (119.6044, 39.9455),
    '钦州市': (108.6388, 21.9734),
    '齐齐哈尔市': (123.9873, 47.3477),
    '七台河市': (131.019, 45.775),
    '泉州市': (118.6004, 24.9017),
    '曲靖市': (103.7825, 25.5208),
    '衢州市': (118.8758, 28.9569),
    '日喀则市': (88.9561, 29.2682),
    '日照市': (119.5072, 35.4202),
    '三门峡市': (111.1813, 34.7833),
    '三明市': (117.6422, 26.2708),
    '厦门市': (118.1039, 24.4892),
    '上海市': (121.4879, 31.2492),
    '商洛市': (109.9342, 33.8739),
    '商丘市': (115.6419, 34.4386),
    '上饶市': (117.9555, 28.4576),
    '山南市': (91.7506, 29.229),
    '汕头市': (116.7287, 23.3839),
    '汕尾市': (115.3729, 22.7787),
    '韶关市': (113.5945, 24.803),
    '绍兴市': (120.5925, 30.0024),
    '邵阳市': (111.4615, 27.2368),
    '嵊州市': (120.831, 29.5614),
    '神农架林区': (110.4872, 31.5958),
    '沈阳市': (123.4328, 41.8086),
    '深圳市': (114.026, 22.5461),
    '石家庄市': (114.5221, 38.049),
    '十堰市': (110.8012, 32.637),
    '石嘴山市': (106.3793, 39.0202),
    '寿光市': (118.7907, 36.8558),
    '双鸭山市': (131.1714, 46.6551),
    '朔州市': (112.4799, 39.3377),
    '四平市': (124.3914, 43.1755),
    '松原市': (124.833, 45.136),
    '绥化市': (126.9891, 46.6461),
    '遂宁市': (105.5649, 30.5575),
    '随州市': (113.3794, 31.7179),
    '宿迁市': (118.2969, 33.952),
    '宿州市': (116.9887, 33.6368),
    '泰安市': (117.0894, 36.1881),
    '台北市': (121.5654, 25.033),
    '台中市': (120.2469, 29.7087),
    '台南市': (120.227, 22.9997),
    '太原市': (112.5509, 37.8903),
    '台州市': (121.4406, 28.6683),
    '唐山市': (118.1835, 39.6505),
    '桃园市': (121.301, 24.9936),
    '天津市': (117.2108, 39.1439),
    '天门市': (113.1262, 30.649),
    '天水市': (105.7369, 34.5843),
    '铁岭市': (123.8548, 42.2998),
    '铜川市': (108.9681, 34.9084),
    '通化市': (125.9427, 41.7364),
    '通辽市': (122.2604, 43.6338),
    '铜陵市': (117.8194, 30.9409),
    '铜仁市': (109.1686, 27.6749),
    '吐鲁番市': (89.266, 42.6789),
    '乌鲁木齐市': (87.565, 43.8404),
    '潍坊市': (119.1426, 36.7161),
    '威海市': (122.094, 37.5288),
    '渭南市': (109.4839, 34.5024),
    '文山壮族苗族自治州': (104.2463, 23.3741),
    '温州市': (120.6906, 28.0028),
    '乌海市': (106.832, 39.6832),
    '武汉市': (114.3162, 30.5811),
    '芜湖市': (118.3841, 31.366),
    '乌兰察布市': (113.1128, 41.0224),
    '武威市': (102.6401, 37.9332),
    '无锡市': (120.3055, 31.57),
    '吴忠市': (106.2083, 37.9936),
    '梧州市': (111.3055, 23.4854),
    '西安市': (108.9531, 34.2778),
    '湘潭市': (112.9356, 27.8351),
    '湘西土家族苗族自治州': (109.7457, 28.318),
    '襄阳市': (112.2501, 32.2292),
    '咸宁市': (114.3001, 29.8807),
    '仙桃市': (113.3874, 30.294),
    '咸阳市': (108.7075, 34.3454),
    '孝感市': (113.9357, 30.928),
    '锡林郭勒盟': (116.0273, 43.9397),
    '兴安盟': (122.0482, 46.0838),
    '邢台市': (114.5205, 37.0695),
    '西宁市': (101.7679, 36.6407),
    '新乡市': (113.9127, 35.3073),
    '信阳市': (114.0855, 32.1286),
    '新余市': (114.9471, 27.8223),
    '忻州市': (112.7279, 38.461),
    '西双版纳傣族自治州': (100.803, 22.0094),
    '宣城市': (118.7521, 30.9516),
    '许昌市': (113.8353, 34.0267),
    '徐州市': (117.1881, 34.2716),
    '雅安市': (103.0094, 29.9997),
    '延安市': (109.5005, 36.6033),
    '延边朝鲜族自治州': (129.4859, 42.8964),
    '盐城市': (120.1489, 33.3799),
    '阳江市': (111.977, 21.8715),
    '杨凌示范区': (108.1027, 34.2696),
    '阳泉市': (113.5692, 37.8695),
    '扬州市': (119.4278, 32.4085),
    '烟台市': (121.3096, 37.5366),
    '宜宾市': (104.633, 28.7697),
    '宜昌市': (111.311, 30.7328),
    '宜春市': (114.4, 27.8111),
    '伊犁哈萨克自治州': (81.2979, 43.9222),
    '银川市': (106.2065, 38.5026),
    '营口市': (122.2334, 40.6687),
    '鹰潭市': (117.0355, 28.2413),
    '义乌市': (120.0751, 29.3068),
    '益阳市': (112.3665, 28.5881),
    '永州市': (111.6146, 26.436),
    '岳阳市': (113.1462, 29.378),
    '榆林市': (109.7459, 36.2794),
    '运城市': (111.0069, 35.0389),
    '云浮市': (112.0509, 22.938),
    '玉树藏族自治州': (97.0133, 33.0062),
    '玉溪市': (102.5451, 24.3704),
    '枣庄市': (117.2793, 34.8079),
    '张家港市': (120.556, 31.8756),
    '张家界市': (110.4816, 29.1249),
    '张家口市': (114.8938, 40.8112),
    '张掖市': (100.4599, 38.9393),
    '漳州市': (117.6762, 24.5171),
    '湛江市': (110.3651, 21.2575),
    '肇庆市': (112.4797, 23.0787),
    '昭通市': (103.725, 27.3406),
    '朝阳市': (120.4462, 41.5718),
    '郑州市': (113.6496, 34.7566),
    '镇江市': (119.4558, 32.2044),
    '中山市': (113.4221, 22.5452),
    '中卫市': (105.1968, 37.5211),
    '周口市': (114.6541, 33.6237),
    '舟山市': (122.1699, 30.036),
    '珠海市': (113.5624, 22.2569),
    '诸暨市': (120.2469, 29.7087),
    '驻马店市': (114.0492, 32.9832),
    '株洲市': (113.1317, 27.8274),
    '淄博市': (118.0591, 36.8047),
    '自贡市': (104.7761, 29.3592),
    '资阳市': (104.6359, 30.1322),
    '遵义市': (106.9313, 27.7),
}


# ============================================================
# 第一模块：天文计算基础
# ============================================================

def julian_day(year: int, month: int, day: float) -> float:
    """计算儒略日（支持格里历）"""
    if month <= 2:
        year -= 1
        month += 12
    A = int(year / 100)
    B = 2 - A + int(A / 4)
    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + B - 1524.5
    return jd


def jd_to_datetime(jd: float) -> datetime:
    """儒略日转公历datetime"""
    jd = jd + 0.5
    Z = int(jd)
    F = jd - Z
    if Z < 2299161:
        A = Z
    else:
        alpha = int((Z - 1867216.25) / 36524.25)
        A = Z + 1 + alpha - int(alpha / 4)
    B = A + 1524
    C = int((B - 122.1) / 365.25)
    D = int(365.25 * C)
    E = int((B - D) / 30.6001)

    day_frac = B - D - int(30.6001 * E) + F
    day = int(day_frac)
    hour_frac = (day_frac - day) * 24
    hour = int(hour_frac)
    min_frac = (hour_frac - hour) * 60
    minute = int(min_frac)
    sec_frac = (min_frac - minute) * 60
    second = int(sec_frac)
    microsecond = int((sec_frac - second) * 1_000_000)

    if E < 14:
        month = E - 1
    else:
        month = E - 13
    if month > 2:
        year = C - 4716
    else:
        year = C - 4715

    return datetime(year, month, day, hour, minute, second, microsecond)


# ============================================================
# 第二模块：真太阳时修正
# ============================================================

def equation_of_time(jd: float) -> float:
    """均时差（分钟）- Jean Meeus算法"""
    T = (jd - 2451545.0) / 36525.0
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    L0 = L0 % 360
    e = 0.016708634 - 0.000042037 * T - 0.0000001267 * T * T
    M = 357.52911 + 35999.05029 * T - 0.0001537 * T * T
    M = math.radians(M % 360)
    eps0 = 23.0 + 26.0/60 + 21.448/3600
    eps0 -= (46.8150/3600) * T - (0.00059/3600) * T*T + (0.001813/3600) * T*T*T
    eps = math.radians(eps0)
    y = math.tan(eps / 2) ** 2
    E = (y * math.sin(2 * math.radians(L0))
         - 2 * e * math.sin(M)
         + 4 * e * y * math.sin(M) * math.cos(2 * math.radians(L0))
         - 0.5 * y * y * math.sin(4 * math.radians(L0))
         - 1.25 * e * e * math.sin(2 * M))
    return math.degrees(E) * 4


def local_to_true_solar_time(dt: datetime, longitude: float, timezone_offset: float = 8.0) -> datetime:
    """地方时转真太阳时"""
    standard_longitude = timezone_offset * 15
    longitude_diff_minutes = (longitude - standard_longitude) * 4
    jd = julian_day(dt.year, dt.month,
                    dt.day + (dt.hour + dt.minute/60 + dt.second/3600 - timezone_offset) / 24)
    eot = equation_of_time(jd)
    total_correction_minutes = longitude_diff_minutes + eot
    true_solar_time = dt + timedelta(minutes=total_correction_minutes)
    return true_solar_time


# ============================================================
# 第三模块：节气计算（VSOP87简化 + 牛顿迭代）
# ============================================================

def sun_apparent_longitude(jd: float) -> float:
    """计算太阳视黄经（度）"""
    T = (jd - 2451545.0) / 36525.0
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    L0 = L0 % 360
    M = 357.52911 + 35999.05029 * T - 0.0001537 * T * T
    M_rad = math.radians(M % 360)
    e = 0.016708634 - 0.000042037 * T - 0.0000001267 * T * T
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M_rad)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M_rad)
         + 0.000289 * math.sin(3 * M_rad))
    sun_lon = L0 + C
    omega = 125.04 - 1934.136 * T
    apparent_lon = sun_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    return apparent_lon % 360


def find_solar_term_jd(year: int, term_index: int) -> float:
    """精确计算指定年份第term_index个节气的儒略日"""
    target_lon = term_index * 15.0
    vernal_equinox_approx = julian_day(year, 3, 20.0)
    jd_estimate = vernal_equinox_approx + (target_lon / 360.0) * 365.25
    for _ in range(50):
        current_lon = sun_apparent_longitude(jd_estimate)
        diff = target_lon - current_lon
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360
        delta_jd = diff / (360.0 / 365.25)
        jd_estimate += delta_jd
        if abs(delta_jd) < 1e-6:
            break
    return jd_estimate


def get_solar_terms_for_range(start_year: int, end_year: int) -> List[Tuple[str, datetime]]:
    """获取指定年份范围内所有节气"""
    all_terms = []
    for year in range(start_year - 1, end_year + 2):
        for name, lon in SOLAR_TERMS_MAP:
            jd = find_solar_term_jd(year, lon // 15)
            dt_utc = jd_to_datetime(jd)
            dt_beijing = dt_utc + timedelta(hours=8)
            all_terms.append((name, dt_beijing))
    all_terms.sort(key=lambda x: x[1])
    filtered = [(n, d) for n, d in all_terms if start_year - 1 <= d.year <= end_year + 1]
    return filtered


# ============================================================
# 第四模块：四柱推算
# ============================================================

def get_year_ganzhi(year: int) -> Tuple[int, int, str]:
    """计算年柱"""
    tg = (year - 4) % 10
    dz = (year - 4) % 12
    return tg, dz, TIANGAN[tg] + DIZHI[dz]


def get_month_ganzhi(year_tg: int, month_index: int) -> Tuple[int, int, str]:
    """计算月柱（以节为界）"""
    month_tg_base = [2, 4, 6, 8, 0]
    base = month_tg_base[year_tg % 5]
    tg = (base + month_index - 1) % 10
    dz = (month_index + 1) % 12
    return tg, dz, TIANGAN[tg] + DIZHI[dz]


def get_day_ganzhi(year: int, month: int, day: int) -> Tuple[int, int, str]:
    """计算日柱（以子夜0点为界）"""
    jd = julian_day(year, month, float(day))
    base_jd = 2451551
    diff = int(jd + 0.5) - base_jd
    tg = diff % 10
    if tg < 0: tg += 10
    dz = diff % 12
    if dz < 0: dz += 12
    return tg, dz, TIANGAN[tg] + DIZHI[dz]


def get_hour_ganzhi(day_tg: int, true_solar_hour: float) -> Tuple[int, int, str]:
    """计算时柱（以真太阳时为准）"""
    if true_solar_hour >= 23 or true_solar_hour < 1:
        dz = 0
    else:
        dz = int((true_solar_hour - 1) // 2) + 1
        dz = dz % 12
    hour_tg_base = [0, 2, 4, 6, 8]
    base = hour_tg_base[day_tg % 5]
    tg = (base + dz) % 10
    return tg, dz, TIANGAN[tg] + DIZHI[dz]


# ============================================================
# 新增计算函数模块
# ============================================================

def get_canggan_list(dz: str) -> Tuple[str, str, str]:
    """获取地支藏干（主气、中气、余气）"""
    canggan = CANGGAN.get(dz, ('', '', ''))
    return canggan[0], canggan[1], canggan[2]  # 主、中、余


def get_shishen_tiangan(yuan: str, other: str) -> str:
    """获取天干十神（日元看其他天干）"""
    return SHISHEN_TIANGAN.get(yuan, {}).get(other, '')


def get_shishen_canggan(yuan: str, dz: str) -> Tuple[str, str, str]:
    """获取藏干十神（日元看地支主气）"""
    shishen_map = SHISHEN_DIZHI_BASE.get(yuan, {})
    shishen_main = shishen_map.get(dz, '')
    # 中气、余气的十神
    _, cg_mid, cg_yu = CANGGAN.get(dz, ('', '', ''))
    shishen_mid = get_shishen_tiangan(yuan, cg_mid) if cg_mid else ''
    shishen_yu = get_shishen_tiangan(yuan, cg_yu) if cg_yu else ''
    return shishen_main, shishen_mid, shishen_yu


def get_changsheng(yuan: str, dz: str) -> str:
    """获取十二长生状态（日元在各地支）"""
    return CHANGSHENG.get(yuan, {}).get(dz, '')


def get_zizuo(tg: str, dz: str) -> str:
    """获取十二长生自坐状态（天干坐本地支）"""
    return ZIZUO.get(tg, {}).get(dz, '')


def get_kongwang(tg_idx: int, dz_idx: int, dz: str) -> str:
    """获取干支所在旬的空亡地支（各柱独立计算）
    六十甲子分6旬,每旬有固定空亡地支:
    旬0 甲子旬(0-9)   → 戌亥空
    旬1 甲戌旬(10-19) → 申酉空
    旬2 甲申旬(20-29) → 午未空
    旬3 甲午旬(30-39) → 辰巳空
    旬4 甲辰旬(40-49) → 寅卯空
    旬5 甲寅旬(50-59) → 子丑空
    返回该旬的空亡地支列表字符串,如"申酉"
    """
    XUN_KONGWANG = {
        0: '戌亥',
        1: '申酉',
        2: '午未',
        3: '辰巳',
        4: '寅卯',
        5: '子丑',
    }
    gz_60 = ganzhi_pair_to_index(tg_idx, dz_idx)
    xun_num = gz_60 // 10
    kw_str = XUN_KONGWANG.get(xun_num, '')
    return kw_str


def get_nayin(tg: str, dz: str) -> str:
    """获取纳音"""
    gz = tg + dz
    return NAYIN_DICT.get(gz, '')


def analyze_wuxing_count(year_tg: str, year_dz: str, month_tg: str, month_dz: str,
                      day_tg: str, day_dz: str, hour_tg: str, hour_dz: str) -> Dict:
    """统计四柱五行数量"""
    # 五行主气数：四柱天干 + 四柱地支主气（各柱各取主气1个）
    wuxing_zhuqi = {
        '木': 0, '火': 0, '土': 0, '金': 0, '水': 0
    }
    for tg in [year_tg, month_tg, day_tg, hour_tg]:
        if tg in TIANGAN:
            wx = WUXING_TIAN[TIANGAN.index(tg)]
            wuxing_zhuqi[wx] += 1
    for dz in [year_dz, month_dz, day_dz, hour_dz]:
        cg_main, _, _ = get_canggan_list(dz)
        if cg_main in TIANGAN:
            wx = WUXING_TIAN[TIANGAN.index(cg_main)]
            wuxing_zhuqi[wx] += 1

    # 五行数（含藏干）：天干五行 + 所有藏干五行
    wuxing_all = {
        '木': 0, '火': 0, '土': 0, '金': 0, '水': 0
    }
    for tg in [year_tg, month_tg, day_tg, hour_tg]:
        if tg in TIANGAN:
            wx = WUXING_TIAN[TIANGAN.index(tg)]
            wuxing_all[wx] += 1
    for dz in [year_dz, month_dz, day_dz, hour_dz]:
        cg_main, cg_mid, cg_yu = get_canggan_list(dz)
        for cg in [cg_main, cg_mid, cg_yu]:
            if cg in TIANGAN:
                wx = WUXING_TIAN[TIANGAN.index(cg)]
                wuxing_all[wx] += 1

    return {
        '五行主气数': wuxing_zhuqi,
        '五行数（含藏干）': wuxing_all,
    }


def analyze_xingchongheha(year_tg: str, year_dz: str, month_tg: str, month_dz: str,
                         day_tg: str, day_dz: str, hour_tg: str, hour_dz: str) -> Dict:
    """分析刑冲合害"""
    tg_list = [year_tg, month_tg, day_tg, hour_tg]
    dz_list = [year_dz, month_dz, day_dz, hour_dz]

    # 天干五合对应的化神五行
    TIANGAN_HE_WX = {
        ('甲', '己'): '土', ('己', '甲'): '土',
        ('乙', '庚'): '金', ('庚', '乙'): '金',
        ('丙', '辛'): '水', ('辛', '丙'): '水',
        ('丁', '壬'): '木', ('壬', '丁'): '木',
        ('戊', '癸'): '火', ('癸', '戊'): '火',
    }

    # 天干合（去重：只记录一次），格式：甲己合土
    tiangan_he = []
    seen_he = set()
    for tg in tg_list:
        if tg in TIANGAN_HE:
            he_tg = TIANGAN_HE[tg]
            if he_tg in tg_list:
                pair = tuple(sorted([tg, he_tg]))
                if pair not in seen_he:
                    seen_he.add(pair)
                    wx = TIANGAN_HE_WX.get((tg, he_tg), '')
                    tiangan_he.append(f"{tg}{he_tg}合{wx}")

    # 地支六合对应的化神五行
    DIZHI_LIUHE_WX = {
        ('子', '丑'): '土', ('丑', '子'): '土',
        ('寅', '亥'): '木', ('亥', '寅'): '木',
        ('卯', '戌'): '火', ('戌', '卯'): '火',
        ('辰', '酉'): '金', ('酉', '辰'): '金',
        ('巳', '申'): '水', ('申', '巳'): '水',
        ('午', '未'): '火土', ('未', '午'): '火土',
    }

    # 六合（去重），格式：午未合火土
    dizhi_liuhe = []
    seen_liuhe = set()
    for dz in dz_list:
        if dz in DIZHI_LIUHE:
            he_dz = DIZHI_LIUHE[dz]
            if he_dz in dz_list:
                pair = tuple(sorted([dz, he_dz]))
                if pair not in seen_liuhe:
                    seen_liuhe.add(pair)
                    wx = DIZHI_LIUHE_WX.get((dz, he_dz), '')
                    dizhi_liuhe.append(f"{dz}{he_dz}合{wx}")

    # 地支三合局（局名）
    SANHE_JU = {
        frozenset(['申', '子', '辰']): '水局',
        frozenset(['巳', '酉', '丑']): '金局',
        frozenset(['寅', '午', '戌']): '火局',
        frozenset(['亥', '卯', '未']): '木局',
    }

    # 三合/半合（不需要三个全部满足，两个即为半合）
    dizhi_sanhe = []
    seen_sanhe = set()
    seen_banhe = set()
    # 三合组
    SANHE_GROUPS = [
        (['申', '子', '辰'], '水局'),
        (['巳', '酉', '丑'], '金局'),
        (['寅', '午', '戌'], '火局'),
        (['亥', '卯', '未'], '木局'),
    ]
    # 半合对（相邻两位组成半合）
    BANHE_PAIRS = {
        ('申', '子'): '申子半合', ('子', '申'): '申子半合',
        ('子', '辰'): '子辰半合', ('辰', '子'): '子辰半合',
        ('申', '辰'): '申辰拱合', ('辰', '申'): '申辰拱合',
        ('巳', '酉'): '巳酉半合', ('酉', '巳'): '巳酉半合',
        ('酉', '丑'): '酉丑半合', ('丑', '酉'): '酉丑半合',
        ('巳', '丑'): '巳丑拱合', ('丑', '巳'): '巳丑拱合',
        ('寅', '午'): '寅午半合', ('午', '寅'): '寅午半合',
        ('午', '戌'): '午戌半合', ('戌', '午'): '午戌半合',
        ('寅', '戌'): '寅戌拱合', ('戌', '寅'): '寅戌拱合',
        ('亥', '卯'): '亥卯半合', ('卯', '亥'): '亥卯半合',
        ('卯', '未'): '卯未半合', ('未', '卯'): '卯未半合',
        ('亥', '未'): '亥未拱合', ('未', '亥'): '亥未拱合',
    }
    for group, ju_name in SANHE_GROUPS:
        present = [d for d in group if d in dz_list]
        if len(present) == 3:
            key = frozenset(group)
            if key not in seen_sanhe:
                seen_sanhe.add(key)
                dizhi_sanhe.append(f"{''.join(group)}三合{ju_name}")
        elif len(present) == 2:
            pair = tuple(sorted(present))
            if pair not in seen_banhe:
                seen_banhe.add(pair)
                label = BANHE_PAIRS.get((present[0], present[1]), '')
                if not label:
                    label = BANHE_PAIRS.get((present[1], present[0]), f"{present[0]}{present[1]}半合")
                dizhi_sanhe.append(label)

    # 暗合：固定对照表（寅丑、卯申、午亥、子巳、寅午、巳酉）
    ANHE_PAIRS = [
        ('寅', '丑'), ('卯', '申'), ('午', '亥'),
        ('子', '巳'), ('寅', '午'), ('巳', '酉'),
    ]
    dizhi_anhe = []
    seen_anhe = set()
    for a, b in ANHE_PAIRS:
        if a in dz_list and b in dz_list:
            pair = (a, b)
            if pair not in seen_anhe:
                seen_anhe.add(pair)
                dizhi_anhe.append(f"{a}{b}暗合")

    # 三刑
    # 无恩之刑：寅巳申（三个全部或任意两个均成立）
    # 恃势之刑：丑未戌（三个全部或任意两个均成立）
    # 无礼之刑：子卯（需要两个全部满足）
    # 自刑：辰辰、午午、酉酉、亥亥（同一地支出现两次）
    dizhi_xing = []
    seen_xing = set()

    # 无恩之刑：寅巳申
    WUEN_GROUP = ['寅', '巳', '申']
    wuen_present = [d for d in WUEN_GROUP if d in dz_list]
    if len(wuen_present) == 3:
        key = frozenset(WUEN_GROUP)
        if key not in seen_xing:
            seen_xing.add(key)
            dizhi_xing.append("寅巳申无恩刑")
    elif len(wuen_present) == 2:
        pair = frozenset(wuen_present)
        if pair not in seen_xing:
            seen_xing.add(pair)
            dizhi_xing.append(f"{''.join(sorted(wuen_present, key=lambda x: WUEN_GROUP.index(x)))}无恩刑")

    # 恃势之刑：丑未戌
    SHISHI_GROUP = ['丑', '未', '戌']
    shishi_present = [d for d in SHISHI_GROUP if d in dz_list]
    if len(shishi_present) == 3:
        key = frozenset(SHISHI_GROUP)
        if key not in seen_xing:
            seen_xing.add(key)
            dizhi_xing.append("丑未戌恃势刑")
    elif len(shishi_present) == 2:
        pair = frozenset(shishi_present)
        if pair not in seen_xing:
            seen_xing.add(pair)
            dizhi_xing.append(f"{''.join(sorted(shishi_present, key=lambda x: SHISHI_GROUP.index(x)))}恃势刑")

    # 无礼之刑：子卯（必须两个都在）
    if '子' in dz_list and '卯' in dz_list:
        key = frozenset(['子', '卯'])
        if key not in seen_xing:
            seen_xing.add(key)
            dizhi_xing.append("子卯无礼刑")

    # 自刑：辰午酉亥按实际数量显示
    for dz in DIZHI_ZIXING:
        count = dz_list.count(dz)
        if count >= 2:
            key = (dz, '自刑', count)
            if key not in seen_xing:
                seen_xing.add(key)
                # 按实际数量显示：2个午=午午自刑，3个午=午午午自刑
                dizhi_str = dz * count
                dizhi_xing.append(f"{dizhi_str}自刑")

    # 六冲（去重），格式：子午冲
    dizhi_chong = []
    seen_chong = set()
    for dz in dz_list:
        if dz in DIZHI_LIUCHONG:
            chong_dz = DIZHI_LIUCHONG[dz]
            if chong_dz in dz_list:
                pair = tuple(sorted([dz, chong_dz]))
                if pair not in seen_chong:
                    seen_chong.add(pair)
                    dizhi_chong.append(f"{dz}{chong_dz}冲")

    # 六害（去重），格式：子未害
    dizhi_hai = []
    seen_hai = set()
    for dz in dz_list:
        if dz in DIZHI_LIUHAI:
            hai_dz = DIZHI_LIUHAI[dz]
            if hai_dz in dz_list:
                pair = tuple(sorted([dz, hai_dz]))
                if pair not in seen_hai:
                    seen_hai.add(pair)
                    dizhi_hai.append(f"{dz}{hai_dz}害")

    # 破（去重），格式：子酉破
    dizhi_po = []
    seen_po = set()
    for dz in dz_list:
        if dz in DIZHI_PO:
            po_dz = DIZHI_PO[dz]
            if po_dz in dz_list:
                pair = tuple(sorted([dz, po_dz]))
                if pair not in seen_po:
                    seen_po.add(pair)
                    dizhi_po.append(f"{dz}{po_dz}破")

    # 三会（需三个全部满足），格式：寅卯辰会木局
    # 三会局定义（含土局辰戌丑未）
    SANHUI_GROUPS = [
        (['寅', '卯', '辰'], '木局'),
        (['巳', '午', '未'], '火局'),
        (['申', '酉', '戌'], '金局'),
        (['亥', '子', '丑'], '水局'),
        (['辰', '戌', '丑', '未'], '土局'),  # 土局四支，需4个全部
    ]
    dizhi_hui = []
    seen_hui = set()
    for group, ju_name in SANHUI_GROUPS:
        if all(d in dz_list for d in group):
            key = frozenset(group)
            if key not in seen_hui:
                seen_hui.add(key)
                dizhi_hui.append(f"{''.join(group)}会{ju_name}")

    def fmt(lst):
        return lst if lst else ['无']

    return {
        '天干五合': fmt(tiangan_he),
        '地支六合': fmt(dizhi_liuhe),
        '地支三合': fmt(dizhi_sanhe),
        '地支暗合': fmt(dizhi_anhe),
        '地支相刑': fmt(dizhi_xing),
        '地支六冲': fmt(dizhi_chong),
        '地支六害': fmt(dizhi_hai),
        '地支相破': fmt(dizhi_po),
        '地支三会': fmt(dizhi_hui),
    }


# ==================== 神煞计算函数 ====================
def calculate_shensha(year_tg: str, year_dz: str, month_tg: str, month_dz: str,
                   day_tg: str, day_dz: str, hour_tg: str, hour_dz: str,
                   year_nayin: str = '', day_kongwang: str = '') -> Dict:
    """计算四柱神煞
    逻辑：每柱的神煞是指 该柱干或支 本身满足某神煞条件
    以日干为基准查各类神煞，判断各柱干支是否命中
    """
    # 导入纳音字典
    from bazi_data import NAYIN_DICT

    # 定义四柱神煞数组（初始为空）
    year_shensha = []
    month_shensha = []
    day_shensha = []
    hour_shensha = []

    # ==================== 天乙贵人 ====================
    # 天乙贵人（以年干、日干分别查四柱地支，命中的地支所在柱有此神煞）
    # 贵人口诀：甲戊庚牛羊, 乙己鼠猴乡, 丙丁猪鸡位, 壬癸兔蛇藏, 六辛逢虎马
    TIANYI = {
        '甲': ['丑', '未'], '乙': ['子', '申'], '丙': ['亥', '酉'],
        '丁': ['亥', '酉'], '戊': ['丑', '未'], '己': ['子', '申'],
        '庚': ['丑', '未'], '辛': ['寅', '午'], '壬': ['卯', '巳'],
        '癸': ['卯', '巳'],
    }
    # 以年干查四柱
    if year_tg in TIANYI:     
        # 年柱：地支有该地支
        if year_dz in TIANYI[year_tg]:
            year_shensha.append('天乙贵人')
        # 月柱：地支有该地支
        if month_dz in TIANYI[year_tg]:
            month_shensha.append('天乙贵人')
        # 日柱：地支有该地支
        if day_dz in TIANYI[year_tg]:
            day_shensha.append('天乙贵人')
        # 时柱：地支有该地支
        if hour_dz in TIANYI[year_tg]:
            hour_shensha.append('天乙贵人')
    # 以日干查四柱
    if day_tg in TIANYI and year_dz in TIANYI[day_tg] and '天乙贵人' not in year_shensha:
        year_shensha.append('天乙贵人')
    if day_tg in TIANYI and month_dz in TIANYI[day_tg] and '天乙贵人' not in month_shensha:
        month_shensha.append('天乙贵人')
    if day_tg in TIANYI and day_dz in TIANYI[day_tg] and '天乙贵人' not in day_shensha:
        day_shensha.append('天乙贵人')
    if day_tg in TIANYI and hour_dz in TIANYI[day_tg] and '天乙贵人' not in hour_shensha:
        hour_shensha.append('天乙贵人')


    # ==================== 天德贵人 ====================
    # 天德贵人（以月支查，命中的天干所在柱有此神煞）
    # 口诀：寅月见丁，卯月见申，辰月见壬，巳月见辛，午月见亥，未月见甲，申月见癸，酉月见寅，戌月见丙，亥月见乙，子月见巳，丑月见庚
    TIANDE_REN = {
        '寅': '丁', '卯': '申', '辰': '壬', '巳': '辛',
        '午': '亥', '未': '甲', '申': '癸', '酉': '寅',
        '戌': '丙', '亥': '乙', '子': '巳', '丑': '庚',
    }
    if month_dz in TIANDE_REN:
        tiande_char = TIANDE_REN[month_dz]
        # 年柱：天干或地支包含该字符
        if year_tg == tiande_char or year_dz == tiande_char:
            year_shensha.append('天德贵人')
        # 月柱：天干或地支包含该字符
        if month_tg == tiande_char or month_dz == tiande_char:
            month_shensha.append('天德贵人')
        # 日柱：天干或地支包含该字符
        if day_tg == tiande_char or day_dz == tiande_char:
            day_shensha.append('天德贵人')
        # 时柱：天干或地支包含该字符
        if hour_tg == tiande_char or hour_dz == tiande_char:
            hour_shensha.append('天德贵人')


    # ==================== 天德合 ====================
    # 天德合（以月支查，命中的天干或地支所在柱有此神煞）
    TIANDE_HE = {
        '寅': '壬', '卯': '巳', '辰': '丁', '巳': '丙',
        '午': '寅', '未': '己', '申': '戊', '酉': '亥',
        '戌': '辛', '亥': '庚', '子': '申', '丑': '乙',
    }
    # 天德合（以月支查，命中的天干或地支所在柱有此神煞）
    if month_dz in TIANDE_HE:
        tiandehe_char = TIANDE_HE[month_dz]
        # 年柱：天干或地支包含该字符
        if year_tg == tiandehe_char or year_dz == tiandehe_char:
            year_shensha.append('天德合')
        # 月柱：天干或地支包含该字符
        if month_tg == tiandehe_char or month_dz == tiandehe_char:
            month_shensha.append('天德合')
        # 日柱：天干或地支包含该字符
        if day_tg == tiandehe_char or day_dz == tiandehe_char:
            day_shensha.append('天德合')
        # 时柱：天干或地支包含该字符
        if hour_tg == tiandehe_char or hour_dz == tiandehe_char:
            hour_shensha.append('天德合')


    # ==================== 月德贵人 ====================
    # 月德贵人（以月支查三合局，命中的天干所在柱有此神煞）
    # 口诀：寅午戌月生者见丙，申子辰月生者见壬，亥卯未月生者见甲，巳酉丑月生者见庚
    # 三合局对应：火局(寅午戌)见丙，水局(申子辰)见壬，木局(亥卯未)见甲，金局(巳酉丑)见庚
    # 查年柱
    if month_dz in ('寅', '午', '戌'):  # 火局见丙
        if year_tg == '丙':
            year_shensha.append('月德贵人')
    elif month_dz in ('申', '子', '辰'):  # 水局见壬
        if year_tg == '壬':
            year_shensha.append('月德贵人')
    elif month_dz in ('亥', '卯', '未'):  # 木局见甲
        if year_tg == '甲':
            year_shensha.append('月德贵人')
    elif month_dz in ('巳', '酉', '丑'):  # 金局见庚
        if year_tg == '庚':
            year_shensha.append('月德贵人')
    # 查月柱
    if month_dz in ('寅', '午', '戌'):  # 火局见丙
        if month_tg == '丙':
            month_shensha.append('月德贵人')
    elif month_dz in ('申', '子', '辰'):  # 水局见壬
        if month_tg == '壬':
            month_shensha.append('月德贵人')
    elif month_dz in ('亥', '卯', '未'):  # 木局见甲
        if month_tg == '甲':
            month_shensha.append('月德贵人')
    elif month_dz in ('巳', '酉', '丑'):  # 金局见庚
        if month_tg == '庚':
            month_shensha.append('月德贵人')
    # 查日柱
    if month_dz in ('寅', '午', '戌'):  # 火局见丙
        if day_tg == '丙':
            day_shensha.append('月德贵人')
    elif month_dz in ('申', '子', '辰'):  # 水局见壬
        if day_tg == '壬':
            day_shensha.append('月德贵人')
    elif month_dz in ('亥', '卯', '未'):  # 木局见甲
        if day_tg == '甲':
            day_shensha.append('月德贵人')
    elif month_dz in ('巳', '酉', '丑'):  # 金局见庚
        if day_tg == '庚':
            day_shensha.append('月德贵人')
    # 查时柱
    if month_dz in ('寅', '午', '戌'):  # 火局见丙
        if hour_tg == '丙':
            hour_shensha.append('月德贵人')
    elif month_dz in ('申', '子', '辰'):  # 水局见壬
        if hour_tg == '壬':
            hour_shensha.append('月德贵人')
    elif month_dz in ('亥', '卯', '未'):  # 木局见甲
        if hour_tg == '甲':
            hour_shensha.append('月德贵人')
    elif month_dz in ('巳', '酉', '丑'):  # 金局见庚
        if hour_tg == '庚':
            hour_shensha.append('月德贵人')


    # ==================== 月德合 ====================
    # 月德合（以月支查三合局，命中的天干所在柱有此神煞）
    # 口诀：寅午戌见辛，申子辰见丁，巳酉丑见乙，亥卯未见己
    # 火局（寅午戌）见辛，水局（申子辰）见丁，金局（巳酉丑）见乙，木局（亥卯未）见己
    # 查年柱
    if month_dz in ('寅', '午', '戌'):  # 火局见辛
        if year_tg == '辛':
            year_shensha.append('月德合')
    elif month_dz in ('申', '子', '辰'):  # 水局见丁
        if year_tg == '丁':
            year_shensha.append('月德合')
    elif month_dz in ('巳', '酉', '丑'):  # 金局见乙
        if year_tg == '乙':
            year_shensha.append('月德合')
    elif month_dz in ('亥', '卯', '未'):  # 木局见己
        if year_tg == '己':
            year_shensha.append('月德合')
    # 查月柱
    if month_dz in ('寅', '午', '戌'):  # 火局见辛
        if month_tg == '辛':
            month_shensha.append('月德合')
    elif month_dz in ('申', '子', '辰'):  # 水局见丁
        if month_tg == '丁':
            month_shensha.append('月德合')
    elif month_dz in ('巳', '酉', '丑'):  # 金局见乙
        if month_tg == '乙':
            month_shensha.append('月德合')
    elif month_dz in ('亥', '卯', '未'):  # 木局见己
        if month_tg == '己':
            month_shensha.append('月德合')
    # 查日柱
    if month_dz in ('寅', '午', '戌'):  # 火局见辛
        if day_tg == '辛':
            day_shensha.append('月德合')
    elif month_dz in ('申', '子', '辰'):  # 水局见丁
        if day_tg == '丁':
            day_shensha.append('月德合')
    elif month_dz in ('巳', '酉', '丑'):  # 金局见乙
        if day_tg == '乙':
            day_shensha.append('月德合')
    elif month_dz in ('亥', '卯', '未'):  # 木局见己
        if day_tg == '己':
            day_shensha.append('月德合')
    # 查时柱
    if month_dz in ('寅', '午', '戌'):  # 火局见辛
        if hour_tg == '辛':
            hour_shensha.append('月德合')
    elif month_dz in ('申', '子', '辰'):  # 水局见丁
        if hour_tg == '丁':
            hour_shensha.append('月德合')
    elif month_dz in ('巳', '酉', '丑'):  # 金局见乙
        if hour_tg == '乙':
            hour_shensha.append('月德合')
    elif month_dz in ('亥', '卯', '未'):  # 木局见己
        if hour_tg == '己':
            hour_shensha.append('月德合')

    # ==================== 文昌贵人 ====================
    # 文昌贵人（以日天干查四柱地支，命中的地支所在柱有此神煞）
    # 口诀：甲乙巳午报君知，丙戊申宫丁己鸡，庚猪辛鼠壬逢虎，癸人见卯入云梯
    # 具体对应：甲见巳，乙见午，丙见申，丁见酉，戊见申，己见酉，庚见亥，辛见子，壬见寅，癸见卯
    WENCHANGREN = {
        '甲': '巳', '乙': '午', '丙': '申', '丁': '酉',
        '戊': '申', '己': '酉', '庚': '亥', '辛': '子',
        '壬': '寅', '癸': '卯',
    }
    # 四柱文昌贵人判断（以日天干查四柱地支）
    if day_tg in WENCHANGREN:
        wenchangren_dz = WENCHANGREN[day_tg]
        # 年柱：地支为该地支
        if year_dz == wenchangren_dz:
            year_shensha.append('文昌贵人')
        # 月柱：地支为该地支
        if month_dz == wenchangren_dz:
            month_shensha.append('文昌贵人')
        # 日柱：地支为该地支
        if day_dz == wenchangren_dz:
            day_shensha.append('文昌贵人')
        # 时柱：地支为该地支
        if hour_dz == wenchangren_dz:
            hour_shensha.append('文昌贵人')

    # ==================== 太极贵人 ====================
    # 太极贵人（以年干和日干分开查年、月、日、时地支）
    TAIJI_GUIDREN_RULES = {
        '甲': ['子', '午'], '乙': ['子', '午'],
        '丙': ['卯', '酉'], '丁': ['卯', '酉'],
        '戊': ['辰', '戌', '丑', '未'], '己': ['辰', '戌', '丑', '未'],
        '庚': ['寅', '亥'], '辛': ['寅', '亥'],
        '壬': ['巳', '申'], '癸': ['巳', '申'],
    }
    # 收集年干和日干对应的所有太极贵人地支（可能不同）
    taiji_guidren_stars = set()
    if year_tg in TAIJI_GUIDREN_RULES:
        taiji_guidren_stars.update(TAIJI_GUIDREN_RULES[year_tg])
    if day_tg in TAIJI_GUIDREN_RULES:
        taiji_guidren_stars.update(TAIJI_GUIDREN_RULES[day_tg])
    # 检查四柱地支是否命中任意一个太极贵人地支
    for taiji in taiji_guidren_stars:
        if year_dz == taiji:
            year_shensha.append('太极贵人')
        if month_dz == taiji:
            month_shensha.append('太极贵人')
        if day_dz == taiji:
            day_shensha.append('太极贵人')
        if hour_dz == taiji:
            hour_shensha.append('太极贵人')

    # ==================== 天厨贵人 ====================
    # 以年干、日干分别查年、月、日、时地支，命中则该柱有天厨贵人
    TIANCHU_GUIDREN_RULES = {
        '甲': '巳',  # 甲见巳
        '乙': '午',  # 乙见午
        '丙': '巳',  # 丙见巳
        '丁': '午',  # 丁见午
        '戊': '申',  # 戊见申
        '己': '酉',  # 己见酉
        '庚': '亥',  # 庚见亥
        '辛': '子',  # 辛见子
        '壬': '寅',  # 壬见寅
        '癸': '卯',  # 癸见卯
    }
    # 收集年干和日干对应的所有天厨贵人地支（可能不同）
    tianchu_guidren_stars = set()
    if year_tg in TIANCHU_GUIDREN_RULES:
        tianchu_guidren_stars.add(TIANCHU_GUIDREN_RULES[year_tg])
    if day_tg in TIANCHU_GUIDREN_RULES:
        tianchu_guidren_stars.add(TIANCHU_GUIDREN_RULES[day_tg])
    # 检查四柱地支是否命中任意一个天厨贵人地支
    for tianchu in tianchu_guidren_stars:
        if year_dz == tianchu:
            year_shensha.append('天厨贵人')
        if month_dz == tianchu:
            month_shensha.append('天厨贵人')
        if day_dz == tianchu:
            day_shensha.append('天厨贵人')
        if hour_dz == tianchu:
            hour_shensha.append('天厨贵人')

    # ==================== 福星贵人 ====================
    # 福星贵人（以年干、日干分别查四柱地支，命中的地支所在柱有此神煞）
    # 贵人口诀：甲丙寅子乙癸丑，戊己申酉丁庚午，辛壬巳辰
    FUXING = {
        '甲': '寅', '丙': '寅', '乙': '丑', '癸': '丑',
        '戊': '申', '己': '申', '丁': '午', '庚': '午',
        '辛': '巳', '壬': '辰',
    }
    # 以年干查四柱地支
    if year_tg in FUXING:
        fuxing_dz = FUXING[year_tg]
        if year_dz == fuxing_dz and '福星贵人' not in year_shensha:
            year_shensha.append('福星贵人')
        if month_dz == fuxing_dz and '福星贵人' not in month_shensha:
            month_shensha.append('福星贵人')
        if day_dz == fuxing_dz and '福星贵人' not in day_shensha:
            day_shensha.append('福星贵人')
        if hour_dz == fuxing_dz and '福星贵人' not in hour_shensha:
            hour_shensha.append('福星贵人')
    # 以日干查四柱地支
    if day_tg in FUXING:
        fuxing_dz = FUXING[day_tg]
        if year_dz == fuxing_dz and '福星贵人' not in year_shensha:
            year_shensha.append('福星贵人')
        if month_dz == fuxing_dz and '福星贵人' not in month_shensha:
            month_shensha.append('福星贵人')
        if day_dz == fuxing_dz and '福星贵人' not in day_shensha:
            day_shensha.append('福星贵人')
        if hour_dz == fuxing_dz and '福星贵人' not in hour_shensha:
            hour_shensha.append('福星贵人')

    # ==================== 德秀贵人 ====================
    # 德秀贵人（依据月地支查其他四柱天干组合）
    # 月支为寅午戌：天干必须满足（丙or丁）and（戊or癸）
    # 月支为申子辰：天干必须满足（壬or癸or戊or己）and（丙or辛or甲or己）
    # 月支为巳酉丑：天干必须满足（庚or辛）and（乙or庚）
    # 月支为亥卯未：天干必须满足（甲or乙）and（丁or壬）
    # 判断四柱天干组合是否满足德秀贵人条件
    all_tiangan = year_tg + month_tg + day_tg + hour_tg  # 四柱天干字符串
    dexiu_cond1 = set()  # 条件1的天干集合
    dexiu_cond2 = set()  # 条件2的天干集合
    has_dexiu = False    # 是否满足德秀贵人条件
    
    if month_dz in ('寅', '午', '戌'):
        dexiu_cond1 = set(('丙', '丁'))
        dexiu_cond2 = set(('戊', '癸'))
    elif month_dz in ('申', '子', '辰'):
        dexiu_cond1 = set(('壬', '癸', '戊', '己'))
        dexiu_cond2 = set(('丙', '辛', '甲', '己'))
    elif month_dz in ('巳', '酉', '丑'):
        dexiu_cond1 = set(('庚', '辛'))
        dexiu_cond2 = set(('乙', '庚'))
    elif month_dz in ('亥', '卯', '未'):
        dexiu_cond1 = set(('甲', '乙'))
        dexiu_cond2 = set(('丁', '壬'))
    
    # 检查四柱天干是否同时满足两个条件
    has_cond1 = any(tg in all_tiangan for tg in dexiu_cond1)
    has_cond2 = any(tg in all_tiangan for tg in dexiu_cond2)
    if has_cond1 and has_cond2:
        has_dexiu = True
    
    # 如果满足德秀贵人条件，逐柱检查该柱天干是否在任意条件集合中
    if has_dexiu:
        if year_tg in dexiu_cond1 or year_tg in dexiu_cond2:
            year_shensha.append('德秀贵人')
        if month_tg in dexiu_cond1 or month_tg in dexiu_cond2:
            month_shensha.append('德秀贵人')
        if day_tg in dexiu_cond1 or day_tg in dexiu_cond2:
            day_shensha.append('德秀贵人')
        if hour_tg in dexiu_cond1 or hour_tg in dexiu_cond2:
            hour_shensha.append('德秀贵人')

    # ==================== 国印贵人 ====================
    # 国印贵人（以年干、日干分别查年、月、日、时地支，命中的地支所在柱有此神煞）
    # 甲见戌，乙见亥，丙见丑，丁见寅，戊见丑，己见寅，庚见辰，辛见巳，壬见未，癸见申
    GUOYIN_GUIDREN_RULES = {
        '甲': '戌',  # 甲见戌
        '乙': '亥',  # 乙见亥
        '丙': '丑',  # 丙见丑
        '丁': '寅',  # 丁见寅
        '戊': '丑',  # 戊见丑
        '己': '寅',  # 己见寅
        '庚': '辰',  # 庚见辰
        '辛': '巳',  # 辛见巳
        '壬': '未',  # 壬见未
        '癸': '申',  # 癸见申
    }
    # 收集年干和日干对应的所有国印贵人地支（可能不同）
    guoyin_guidren_dzs = set()
    if year_tg in GUOYIN_GUIDREN_RULES:
        guoyin_guidren_dzs.add(GUOYIN_GUIDREN_RULES[year_tg])
    if day_tg in GUOYIN_GUIDREN_RULES:
        guoyin_guidren_dzs.add(GUOYIN_GUIDREN_RULES[day_tg])
    # 检查四柱地支是否命中任意一个国印贵人地支
    for guoyin in guoyin_guidren_dzs:
        if year_dz == guoyin:
            year_shensha.append('国印贵人')
        if month_dz == guoyin:
            month_shensha.append('国印贵人')
        if day_dz == guoyin:
            day_shensha.append('国印贵人')
        if hour_dz == guoyin:
            hour_shensha.append('国印贵人')

    # ==================== 咸池 ====================
    # 咸池（桃花，以年地支或日地支查年、月、日、时柱地支，命中的地支所在柱有此神煞）
    # 若年支或日支为申、子、辰，其余地支中见酉，则该柱有咸池
    # 若年支或日支为寅、午、戌，其余地支中见卯，则该柱有咸池
    # 若年支或日支为巳、酉、丑，其余地支中见午，则该柱有咸池
    # 若年支或日支为亥、卯、未，其余地支中见子，则该柱有咸池
    # 确定年支和日支对应的桃花地支
    if year_dz in ('申', '子', '辰') or day_dz in ('申', '子', '辰'):
        # 年柱：地支为酉
        if year_dz == '酉':
            year_shensha.append('咸池')
        # 月柱：地支为酉
        if month_dz == '酉':
            month_shensha.append('咸池')
        # 日柱：地支为酉
        if day_dz == '酉':
            day_shensha.append('咸池')
        # 时柱：地支为酉
        if hour_dz == '酉':
            hour_shensha.append('咸池')
    if year_dz in ('寅', '午', '戌') or day_dz in ('寅', '午', '戌'):
        # 年柱：地支为卯
        if year_dz == '卯':
            year_shensha.append('咸池')
        # 月柱：地支为卯
        if month_dz == '卯':
            month_shensha.append('咸池')
        # 日柱：地支为卯
        if day_dz == '卯':
            day_shensha.append('咸池')
        # 时柱：地支为卯
        if hour_dz == '卯':
            hour_shensha.append('咸池')
    if year_dz in ('巳', '酉', '丑') or day_dz in ('巳', '酉', '丑'):
        # 年柱：地支为午
        if year_dz == '午':
            year_shensha.append('咸池')
        # 月柱：地支为午
        if month_dz == '午':
            month_shensha.append('咸池')
        # 日柱：地支为午
        if day_dz == '午':
            day_shensha.append('咸池')
        # 时柱：地支为午
        if hour_dz == '午':
            hour_shensha.append('咸池')
    if year_dz in ('亥', '卯', '未') or day_dz in ('亥', '卯', '未'):
        # 年柱：地支为子
        if year_dz == '子':
            year_shensha.append('咸池')
        # 月柱：地支为子
        if month_dz == '子':
            month_shensha.append('咸池')
        # 日柱：地支为子
        if day_dz == '子':
            day_shensha.append('咸池')
        # 时柱：地支为子
        if hour_dz == '子':
            hour_shensha.append('咸池')

    # ==================== 纳音桃花 ====================
    # 以年柱纳音五行查四柱地支，命中的地支所在柱有此神煞
    # 年柱纳音为金：地支见巳或亥
    # 年柱纳音为木：地支见亥或卯
    # 年柱纳音为火：地支见申或子
    # 年柱纳音为水：地支见戌或午
    # 年柱纳音为土：地支见戌或午
    if year_nayin:
        # 取纳音最后一个字为五行
        nayin_wuxing = year_nayin[-1]
        NAYIN_TAOHUA = {
            '金': ('巳', '亥'),
            '木': ('亥', '卯'),
            '火': ('申', '子'),
            '水': ('戌', '午'),
            '土': ('戌', '午'),
        }
        if nayin_wuxing in NAYIN_TAOHUA:
            taohua_dzs = NAYIN_TAOHUA[nayin_wuxing]
            if year_dz in taohua_dzs:
                year_shensha.append('纳音桃花')
            if month_dz in taohua_dzs:
                month_shensha.append('纳音桃花')
            if day_dz in taohua_dzs:
                day_shensha.append('纳音桃花')
            if hour_dz in taohua_dzs:
                hour_shensha.append('纳音桃花')

    # ==================== 魁罡 ====================
    # 只查日柱，日柱天干地支合并为 戊戌、庚辰、庚戌、壬辰 之一即为魁罡
    KUIGANG = {'戊戌', '庚辰', '庚戌', '壬辰'}
    if (day_tg + day_dz) in KUIGANG:
        day_shensha.append('魁罡')

    # ==================== 禄神 ====================
    # 以日干查年、月、日、时柱地支，命中则该柱有禄神
    LUSHEN = {
        '甲': '寅', '乙': '卯',
        '丙': '巳', '丁': '午',
        '戊': '巳', '己': '午',
        '庚': '申', '辛': '酉',
        '壬': '亥', '癸': '子',
    }
    if day_tg in LUSHEN:
        lu_dz = LUSHEN[day_tg]
        if year_dz == lu_dz:
            year_shensha.append('禄神')
        if month_dz == lu_dz:
            month_shensha.append('禄神')
        if day_dz == lu_dz:
            day_shensha.append('禄神')
        if hour_dz == lu_dz:
            hour_shensha.append('禄神')

    # ==================== 天喜 ====================
    # 天喜（以年支查年、月、日、时支，命中则该柱有天喜）
    TIANXI = {
        '子': '酉',  # 子见酉
        '丑': '申',  # 丑见申
        '寅': '未',  # 寅见未
        '卯': '午',  # 卯见午
        '辰': '巳',  # 辰见巳
        '巳': '辰',  # 巳见辰
        '午': '卯',  # 午见卯
        '未': '寅',  # 未见寅
        '申': '丑',  # 申见丑
        '酉': '子',  # 酉见子
        '戌': '亥',  # 戌见亥
        '亥': '戌',  # 亥见戌
    }
    if year_dz in TIANXI:
        tianxi_dz = TIANXI[year_dz]
        if year_dz == tianxi_dz:
            year_shensha.append('天喜')
        if month_dz == tianxi_dz:
            month_shensha.append('天喜')
        if day_dz == tianxi_dz:
            day_shensha.append('天喜')
        if hour_dz == tianxi_dz:
            hour_shensha.append('天喜')

    # ==================== 红鸾 ====================
    # 红鸾（以年支查年、月、日、时支，命中则该柱有红鸾）
    HONGLUAN = {
        '子': '卯',  # 子见卯
        '丑': '寅',  # 丑见寅
        '寅': '丑',  # 寅见丑
        '卯': '子',  # 卯见子
        '辰': '亥',  # 辰见亥
        '巳': '戌',  # 巳见戌
        '午': '酉',  # 午见酉
        '未': '申',  # 未见申
        '申': '未',  # 申见未
        '酉': '午',  # 酉见午
        '戌': '巳',  # 戌见巳
        '亥': '辰',  # 亥见辰
    }
    if year_dz in HONGLUAN:
        hongluan_dz = HONGLUAN[year_dz]
        if year_dz == hongluan_dz:
            year_shensha.append('红鸾')
        if month_dz == hongluan_dz:
            month_shensha.append('红鸾')
        if day_dz == hongluan_dz:
            day_shensha.append('红鸾')
        if hour_dz == hongluan_dz:
            hour_shensha.append('红鸾')

    # ==================== 十灵日 ====================
    # 只查日柱，日柱天干地支合并为指定组合之一即为十灵日
    SHILINGRI = {'甲辰', '乙亥', '丙辰', '丁酉', '戊午', '庚戌', '庚寅', '辛亥', '壬寅', '癸未'}
    if (day_tg + day_dz) in SHILINGRI:
        day_shensha.append('十灵日')

    # ==================== 六秀日 ====================
    # 以日干查年、月、日、时地支，命中则该柱有六秀日
    GULUAN = {'丙午', '丁未', '戊子', '戊午', '己丑', '己未'}
    if (day_tg + day_dz) in SHILINGRI:
        day_shensha.append('六秀日')

    # ==================== 四废日 ====================
    # 四废日（以月支查日柱，命中则日柱有四废日）
    # 寅卯辰月：日柱为庚申或辛酉
    # 巳午未月：日柱为壬子或癸亥
    # 申酉戌月：日柱为甲寅或乙卯
    # 亥子丑月：日柱为丙午或丁巳
    day_ganzhi = day_tg + day_dz
    if month_dz in ('寅', '卯', '辰'):
        if day_ganzhi in ('庚申', '辛酉'):
            day_shensha.append('四废日')
    elif month_dz in ('巳', '午', '未'):
        if day_ganzhi in ('壬子', '癸亥'):
            day_shensha.append('四废日')
    elif month_dz in ('申', '酉', '戌'):
        if day_ganzhi in ('甲寅', '乙卯'):
            day_shensha.append('四废日')
    elif month_dz in ('亥', '子', '丑'):
        if day_ganzhi in ('丙午', '丁巳'):
            day_shensha.append('四废日')

    # ==================== 羊刃 ====================
    # 以日干查年、月、日、时柱地支，命中则该柱有羊刃
    YANGREN = {
        '甲': '卯', '乙': '寅',
        '丙': '午', '丁': '巳',
        '戊': '午', '己': '巳',
        '庚': '酉', '辛': '申',
        '壬': '子', '癸': '亥',
    }
    if day_tg in YANGREN:
        yangren_dz = YANGREN[day_tg]
        if year_dz == yangren_dz:
            year_shensha.append('羊刃')
        if month_dz == yangren_dz:
            month_shensha.append('羊刃')
        if day_dz == yangren_dz:
            day_shensha.append('羊刃')
        if hour_dz == yangren_dz:
            hour_shensha.append('羊刃')
    
    # ==================== 飞刃 ====================
    # 以日干查年、月、日、时地支，命中则该柱有飞刃
    FEIREN = {
        '甲': '酉',
        '乙': '申',
        '丙': '子',
        '丁': '亥',
        '戊': '子',
        '己': '亥',
        '庚': '卯',
        '辛': '寅',
        '壬': '午',
        '癸': '巳',
    }
    if day_tg in FEIREN:
        feiren_dz = FEIREN[day_tg]
        if year_dz == feiren_dz:
            year_shensha.append('飞刃')
        if month_dz == feiren_dz:
            month_shensha.append('飞刃')
        if day_dz == feiren_dz:
            day_shensha.append('飞刃')
        if hour_dz == feiren_dz:
            hour_shensha.append('飞刃')

    # ==================== 血刃 ====================
    # 以月支查年、月、日、时地支，命中则该柱有血刃
    XUEREN = {
        '寅': '丑',
        '卯': '未',
        '辰': '寅',
        '巳': '申',
        '午': '卯',
        '未': '酉',
        '申': '辰',
        '酉': '戌',
        '戌': '巳',
        '亥': '亥',
        '子': '午',
        '丑': '子',
    }
    if month_dz in XUEREN:
        xueren_dz = XUEREN[month_dz]
        if year_dz == xueren_dz:
            year_shensha.append('血刃')
        if month_dz == xueren_dz:
            month_shensha.append('血刃')
        if day_dz == xueren_dz:
            day_shensha.append('血刃')
        if hour_dz == xueren_dz:
            hour_shensha.append('血刃')

    # ==================== 流霞 ====================
    # 以日干查年、月、日、时地支，命中则该柱有流霞
    LIUXIA = {
        '甲': '酉',
        '乙': '戌',
        '丙': '未',
        '丁': '申',
        '戊': '巳',
        '己': '午',
        '庚': '辰',
        '辛': '卯',
        '壬': '亥',
        '癸': '寅',
    }
    if day_tg in LIUXIA:
        liuxia_dz = LIUXIA[day_tg]
        if year_dz == liuxia_dz:
            year_shensha.append('流霞')
        if month_dz == liuxia_dz:
            month_shensha.append('流霞')
        if day_dz == liuxia_dz:
            day_shensha.append('流霞')
        if hour_dz == liuxia_dz:
            hour_shensha.append('流霞')

    # ==================== 驿马 ====================
    # 以年支、日支查年、月、日、时柱地支，命中则该柱有驿马
    # 申子辰三合见寅, 寅午戌三合见申, 巳酉丑三合见亥, 亥卯未三合见巳
    SANHE_YIMA = {
        ('申', '子', '辰'): '寅',
        ('寅', '午', '戌'): '申',
        ('巳', '酉', '丑'): '亥',
        ('亥', '卯', '未'): '巳',
    }
    # 收集年支和日支所在三合局的所有驿马星（可能不同）
    yima_stars = set()
    for sanhe, yima in SANHE_YIMA.items():
        if year_dz in sanhe:
            yima_stars.add(yima)
        if day_dz in sanhe:
            yima_stars.add(yima)
    # 检查四柱地支是否命中任意一个驿马星
    for yima in yima_stars:
        if year_dz == yima:
            year_shensha.append('驿马')
        if month_dz == yima:
            month_shensha.append('驿马')
        if day_dz == yima:
            day_shensha.append('驿马')
        if hour_dz == yima:
            hour_shensha.append('驿马')

    # ==================== 阴差阳错 ====================
    # 只查日柱，日柱天干地支合并为指定组合之一即为阴差阳错
    YINCHAYANGCUO = {'丙子', '丙午', '丁丑', '丁未', '戊寅', '戊申',
                     '辛卯', '辛酉', '壬辰', '壬戌', '癸巳', '癸亥'}
    if (day_tg + day_dz) in YINCHAYANGCUO:
        day_shensha.append('阴差阳错')

    # ==================== 孤辰 ====================
    # 以年支查月、日、时地支，命中则该柱有孤辰
    GUCHEN_RULES = {
        '亥': '寅',
        '子': '寅',
        '丑': '寅',
        '寅': '巳',
        '卯': '巳',
        '辰': '巳',
        '巳': '申',
        '午': '申',
        '未': '申',
        '申': '亥',
        '酉': '亥',
        '戌': '亥',
    }
    if year_dz in GUCHEN_RULES:
        guchen_dz = GUCHEN_RULES[year_dz]
        if month_dz == guchen_dz:
            month_shensha.append('孤辰')
        if day_dz == guchen_dz:
            day_shensha.append('孤辰')
        if hour_dz == guchen_dz:
            hour_shensha.append('孤辰')

    # ==================== 寡宿 ====================
    # 以年支查月、日、时地支，命中则该柱有寡宿
    GUASU_RULES = {
        '亥': '戌',
        '子': '戌',
        '丑': '戌',
        '寅': '丑',
        '卯': '丑',
        '辰': '丑',
        '巳': '辰',
        '午': '辰',
        '未': '辰',
        '申': '未',
        '酉': '未',
        '戌': '未',
    }
    if year_dz in GUASU_RULES:
        guasu_dz = GUASU_RULES[year_dz]
        if month_dz == guasu_dz:
            month_shensha.append('寡宿')
        if day_dz == guasu_dz:
            day_shensha.append('寡宿')
        if hour_dz == guasu_dz:
            hour_shensha.append('寡宿')

    # ==================== 空亡 ====================
    # 以日柱所在旬的空亡地支查四柱地支，命中则该柱有空亡神煞
    if day_kongwang:
        # day_kongwang 格式为 "戌亥"、"申酉" 等
        if year_dz in day_kongwang:
            year_shensha.append('空亡')
        if month_dz in day_kongwang:
            month_shensha.append('空亡')
        if day_dz in day_kongwang:
            day_shensha.append('空亡')
        if hour_dz in day_kongwang:
            hour_shensha.append('空亡')

    # ==================== 十恶大败 ====================
    # 只查日柱，日柱天干地支合并为指定组合之一即为十恶大败
    SHIWEDABAI = {'甲辰', '乙巳', '丙申', '丁亥', '庚辰', '戊戌', '癸亥', '辛巳', '己丑', '壬申'}
    if (day_tg + day_dz) in SHIWEDABAI:
        day_shensha.append('十恶大败')

    # ==================== 八专 ====================
    # 只查日柱，日柱天干地支合并为指定组合之一即为八专
    BAZHUAN = {'甲寅', '乙卯', '丁未', '戊戌', '己未', '庚申', '辛酉', '癸丑'}
    if (day_tg + day_dz) in BAZHUAN:
        day_shensha.append('八专')

    # ==================== 九丑 ====================
    # 只查日柱，日柱天干地支合并为指定组合之一即为九丑
    JIUCHOU = {'丁酉', '戊子', '戊午', '己卯', '己酉', '辛卯', '辛酉', '壬子', '壬午'}
    if (day_tg + day_dz) in JIUCHOU:
        day_shensha.append('九丑')
   
    # ==================== 孤鸾煞 ====================
    # 只查日柱，日柱天干地支合并为指定组合之一即为孤鸾煞
    GULUAN = {'甲寅', '乙巳', '丙午', '丁巳', '戊午', '戊申', '辛亥', '壬子'}
    if (day_tg + day_dz) in GULUAN:
        day_shensha.append('孤鸾煞')


    # ==================== 红艳煞 ====================
    # 以日干查年、月、日、时地支，命中则该柱有红艳煞
    HONGYAN_SHA = {
        '甲': '午',
        '乙': '午',
        '丙': '寅',
        '丁': '未',
        '戊': '辰',
        '己': '辰',
        '庚': '戌',
        '辛': '酉',
        '壬': '子',
        '癸': '申',
    }
    if day_tg in HONGYAN_SHA:
        target_dz = HONGYAN_SHA[day_tg]
        if year_dz == target_dz:
            year_shensha.append('红艳煞')
        if month_dz == target_dz:
            month_shensha.append('红艳煞')
        if day_dz == target_dz:
            day_shensha.append('红艳煞')
        if hour_dz == target_dz:
            hour_shensha.append('红艳煞')

    # ==================== 学堂 ====================
    # 以年柱纳音五行查月、日、时柱地支，命中则该柱有学堂神煞
    # 额外判断：若命中地支对应的干支为特定组合，则学堂升级为"正学堂"
    if year_nayin:
        nayin_wuxing = year_nayin[-1]
        XUETANG_RULES = {
            '金': ('巳', '辛巳'),
            '木': ('亥', '己亥'),
            '水': ('申', '甲申'),
            '土': ('申', '戊申'),
            '火': ('寅', '丙寅'),
        }
        if nayin_wuxing in XUETANG_RULES:
            xuetang_dz, zheng_xuetang_gz = XUETANG_RULES[nayin_wuxing]
            # 月柱
            if month_dz == xuetang_dz:
                month_gz = month_tg + month_dz
                if month_gz == zheng_xuetang_gz:
                    month_shensha.append('正学堂')
                else:
                    month_shensha.append('学堂')
            # 日柱
            if day_dz == xuetang_dz:
                day_gz = day_tg + day_dz
                if day_gz == zheng_xuetang_gz:
                    day_shensha.append('正学堂')
                else:
                    day_shensha.append('学堂')
            # 时柱
            if hour_dz == xuetang_dz:
                hour_gz = hour_tg + hour_dz
                if hour_gz == zheng_xuetang_gz:
                    hour_shensha.append('正学堂')
                else:
                    hour_shensha.append('学堂')

    # ==================== 词馆 ====================
    # 以年柱纳音五行查月、日、时柱地支，命中则该柱有词馆神煞
    # 额外判断：若命中地支对应的干支为特定组合，则词馆升级为"正词馆"
    if year_nayin:
        nayin_wuxing = year_nayin[-1]
        CIGUAN_RULES = {
            '金': ('申', '壬申'),
            '木': ('寅', '庚寅'),
            '水': ('亥', '癸亥'),
            '土': ('亥', '丁亥'),
            '火': ('巳', '乙巳'),
        }
        if nayin_wuxing in CIGUAN_RULES:
            cigan_dz, zheng_cigan_gz = CIGUAN_RULES[nayin_wuxing]
            # 月柱
            if month_dz == cigan_dz:
                month_gz = month_tg + month_dz
                if month_gz == zheng_cigan_gz:
                    month_shensha.append('正词馆')
                else:
                    month_shensha.append('词馆')
            # 日柱
            if day_dz == cigan_dz:
                day_gz = day_tg + day_dz
                if day_gz == zheng_cigan_gz:
                    day_shensha.append('正词馆')
                else:
                    day_shensha.append('词馆')
            # 时柱
            if hour_dz == cigan_dz:
                hour_gz = hour_tg + hour_dz
                if hour_gz == zheng_cigan_gz:
                    hour_shensha.append('正词馆')
                else:
                    hour_shensha.append('词馆')

    # ==================== 将星 ====================
    # 年支查月、日、时地支，日支查年、月、时地支，命中则该柱有将星
    JIANGXING_RULES = {
        '申': '子', '子': '子', '辰': '子',  # 申子辰见子
        '巳': '酉', '酉': '酉', '丑': '酉',  # 巳酉丑见酉
        '寅': '午', '午': '午', '戌': '午',  # 寅午戌见午
        '亥': '卯', '卯': '卯', '未': '卯'   # 亥卯未见卯
    }
    # 以年支查月、日、时地支
    if year_dz in JIANGXING_RULES:
        year_jiangxing = JIANGXING_RULES[year_dz]
        if month_dz == year_jiangxing:
            month_shensha.append('将星')
        if day_dz == year_jiangxing:
            day_shensha.append('将星')
        if hour_dz == year_jiangxing:
            hour_shensha.append('将星')
    # 以日支查年、月、时地支
    if day_dz in JIANGXING_RULES:
        day_jiangxing = JIANGXING_RULES[day_dz]
        if year_dz == day_jiangxing:
            year_shensha.append('将星')
        if month_dz == day_jiangxing:
            month_shensha.append('将星')
        if hour_dz == day_jiangxing:
            hour_shensha.append('将星')

    # ==================== 金舆 ====================
    # 以日干查年、月、日、时地支，命中则该柱有金舆
    JINYU_RULES = {
        '甲': '辰',      # 甲见辰
        '乙': '巳',      # 乙见巳
        '丙': '未',      # 丙或戊见未
        '丁': '未',      # 丁见未
        '戊': '未',      # 丙或戊见未
        '己': '申',      # 己见申
        '庚': '戌',      # 庚见戌
        '辛': '亥',      # 辛见亥
        '壬': '丑',      # 壬见丑
        '癸': '寅',      # 癸见寅
    }
    if day_tg in JINYU_RULES:
        jinyu_dz = JINYU_RULES[day_tg]
        if year_dz == jinyu_dz:
            year_shensha.append('金舆')
        if month_dz == jinyu_dz:
            month_shensha.append('金舆')
        if day_dz == jinyu_dz:
            day_shensha.append('金舆')
        if hour_dz == jinyu_dz:
            hour_shensha.append('金舆')

    # ==================== 华盖 ====================
    # 以年支、日支分开查年、月、日、时柱地支，命中则该柱有华盖
    # 寅午戌见戌, 亥卯未见未, 巳酉丑见丑, 申子辰见辰
    HUAGAI_RULES = {
        ('寅', '午', '戌'): '戌',
        ('亥', '卯', '未'): '未',
        ('巳', '酉', '丑'): '丑',
        ('申', '子', '辰'): '辰',
    }
    # 收集年支和日支对应的所有华盖地支（可能不同）
    huagai_stars = set()
    for sanhe, huagai in HUAGAI_RULES.items():
        if year_dz in sanhe:
            huagai_stars.add(huagai)
        if day_dz in sanhe:
            huagai_stars.add(huagai)
    # 检查四柱地支是否命中任意一个华盖地支
    for huagai in huagai_stars:
        if year_dz == huagai:
            year_shensha.append('华盖')
        if month_dz == huagai:
            month_shensha.append('华盖')
        if day_dz == huagai:
            day_shensha.append('华盖')
        if hour_dz == huagai:
            hour_shensha.append('华盖')
                        
    # ==================== 劫煞 ====================
    # 以年支、日支查年、月、日、时柱地支，命中则该柱有劫煞
    # 寅午戌见亥, 亥卯未见申, 巳酉丑见寅, 申子辰见巳
    JIESHA_RULES = {
        ('寅', '午', '戌'): '亥',
        ('亥', '卯', '未'): '申',
        ('巳', '酉', '丑'): '寅',
        ('申', '子', '辰'): '巳',
    }
    # 收集年支和日支对应的所有劫煞地支（可能不同）
    jiesha_stars = set()
    for sanhe, jiesha in JIESHA_RULES.items():
        if year_dz in sanhe:
            jiesha_stars.add(jiesha)
        if day_dz in sanhe:
            jiesha_stars.add(jiesha)
    # 检查四柱地支是否命中任意一个劫煞地支
    for jiesha in jiesha_stars:
        if year_dz == jiesha:
            year_shensha.append('劫煞')
        if month_dz == jiesha:
            month_shensha.append('劫煞')
        if day_dz == jiesha:
            day_shensha.append('劫煞')
        if hour_dz == jiesha:
            hour_shensha.append('劫煞')

    # ==================== 灾煞 ====================
    # 以年支查月、日、时柱地支，命中则该柱有灾煞
    # 寅午戌见子, 亥卯未见酉, 巳酉丑见卯, 申子辰见午
    ZAISHA_RULES = {
        ('寅', '午', '戌'): '子',
        ('亥', '卯', '未'): '酉',
        ('巳', '酉', '丑'): '卯',
        ('申', '子', '辰'): '午',
    }
    # 收集年支对应的灾煞地支
    zaisha_stars = set()
    for sanhe, zaisha in ZAISHA_RULES.items():
        if year_dz in sanhe:
            zaisha_stars.add(zaisha)
    # 检查月、日、时柱地支是否命中任意一个灾煞地支
    for zaisha in zaisha_stars:
        if month_dz == zaisha:
            month_shensha.append('灾煞')
        if day_dz == zaisha:
            day_shensha.append('灾煞')
        if hour_dz == zaisha:
            hour_shensha.append('灾煞')

    # ==================== 亡神 ====================
    # 以年支、日支查年、月、日、时柱地支，命中则该柱有亡神
    # 寅午戌三合见巳, 亥卯未三合见寅, 巳酉丑三合见申, 申子辰三合见亥
    WANGSHEN_RULES = {
        ('寅', '午', '戌'): '巳',
        ('亥', '卯', '未'): '寅',
        ('巳', '酉', '丑'): '申',
        ('申', '子', '辰'): '亥',
    }
    # 收集年支和日支对应的所有亡神地支（可能不同）
    wangshen_stars = set()
    for sanhe, wangshen in WANGSHEN_RULES.items():
        if year_dz in sanhe:
            wangshen_stars.add(wangshen)
        if day_dz in sanhe:
            wangshen_stars.add(wangshen)
    # 检查四柱地支是否命中任意一个亡神地支
    for wangshen in wangshen_stars:
        if year_dz == wangshen:
            year_shensha.append('亡神')
        if month_dz == wangshen:
            month_shensha.append('亡神')
        if day_dz == wangshen:
            day_shensha.append('亡神')
        if hour_dz == wangshen:
            hour_shensha.append('亡神')


    # ==================== 丧门吊客披麻 ====================
    # 以年支查月、日、时地支，命中则该柱有对应神煞
    # 丧门：年支前两位，吊客：年支后两位，披麻：年支后三位
    DIZHI_ORDER = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
    sangmen_index = (DIZHI_ORDER.index(year_dz) + 2) % 12  # 前两位
    diaoke_index = (DIZHI_ORDER.index(year_dz) - 2) % 12  # 后两位
    pima_index = (DIZHI_ORDER.index(year_dz) - 3) % 12      # 后三位
    sangmen = DIZHI_ORDER[sangmen_index]
    diaoke = DIZHI_ORDER[diaoke_index]
    pima = DIZHI_ORDER[pima_index]
    # 查月柱地支
    if month_dz == sangmen:
        month_shensha.append('丧门')
    if month_dz == diaoke:
        month_shensha.append('吊客')
    if month_dz == pima:
        month_shensha.append('披麻')
    # 查日柱地支
    if day_dz == sangmen:
        day_shensha.append('丧门')
    if day_dz == diaoke:
        day_shensha.append('吊客')
    if day_dz == pima:
        day_shensha.append('披麻')
    # 查时柱地支
    if hour_dz == sangmen:
        hour_shensha.append('丧门')
    if hour_dz == diaoke:
        hour_shensha.append('吊客')
    if hour_dz == pima:
        hour_shensha.append('披麻')

    # 构建返回结果
    result = {
        '年柱': year_shensha if year_shensha else ['无'],
        '月柱': month_shensha if month_shensha else ['无'],
        '日柱': day_shensha if day_shensha else ['无'],
        '时柱': hour_shensha if hour_shensha else ['无'],
    }

    return result


def calculate_dayun_shensha(dayun_tg: str, dayun_dz: str,
                              day_tg: str, day_dz: str,
                              year_tg: str, year_dz: str,
                              month_tg: str, month_dz: str,
                              hour_tg: str, hour_dz: str,
                              year_nayin: str = '') -> List[str]:
    """计算大运神煞（将大运干支看作单柱，按照四柱神煞的标准计算）"""
    ss = []

    # ==================== 天乙贵人 ====================
    # 口诀：甲戊庚牛羊, 乙己鼠猴乡, 丙丁猪鸡位, 壬癸兔蛇藏, 六辛逢虎马
    # 以年干、日干分别查大运地支，命中则有天乙贵人
    TIANYI = {
        '甲': ['丑', '未'], '乙': ['子', '申'], '丙': ['亥', '酉'],
        '丁': ['亥', '酉'], '戊': ['丑', '未'], '己': ['子', '申'],
        '庚': ['丑', '未'], '辛': ['寅', '午'], '壬': ['卯', '巳'],
        '癸': ['卯', '巳'],
    }
    # 以年干查大运地支
    if year_tg in TIANYI and dayun_dz in TIANYI[year_tg]:
        ss.append('天乙贵人')
    # 以日干查大运地支（避免重复添加）
    if day_tg in TIANYI and dayun_dz in TIANYI[day_tg] and '天乙贵人' not in ss:
        ss.append('天乙贵人')

    # ==================== 天德贵人 ====================
    # 口诀：寅丁卯申辰壬巳辛，午亥未甲申癸酉寅，戌丙亥乙子巳丑庚
    # 以月支查大运干支（天干和地支都要看），命中则有天德贵人
    TIANDE = {
        '寅': '丁', '卯': '申', '辰': '壬', '巳': '辛',
        '午': '亥', '未': '甲', '申': '癸', '酉': '寅',
        '戌': '丙', '亥': '乙', '子': '巳', '丑': '庚',
    }
    if month_dz in TIANDE:
        tiande_val = TIANDE[month_dz]
        # 大运天干或地支中有对应字符，则命中
        if dayun_tg == tiande_val or dayun_dz == tiande_val:
            ss.append('天德贵人')

    # ==================== 天德合 ====================
    # 以月支查天德合字典，检查大运天干或地支是否包含对应字符
    TIANDEHE = {
        '寅': '壬', '卯': '巳', '辰': '丁', '巳': '丙',
        '午': '寅', '未': '己', '申': '戊', '酉': '亥',
        '戌': '辛', '亥': '庚', '子': '申', '丑': '乙',
    }
    if month_dz in TIANDEHE:
        tiandehe_val = TIANDEHE[month_dz]
        if dayun_tg == tiandehe_val or dayun_dz == tiandehe_val:
            ss.append('天德合')

    # ==================== 月德贵人 ====================
    # 以月支查大运天干，条件：寅午戌见丙，申子辰见壬，亥卯未见甲，巳酉丑见庚
    YUANDE = {
        ('寅', '午', '戌'): '丙',
        ('申', '子', '辰'): '壬',
        ('亥', '卯', '未'): '甲',
        ('巳', '酉', '丑'): '庚',
    }
    for dzs, tg_val in YUANDE.items():
        if month_dz in dzs and dayun_tg == tg_val:
            ss.append('月德贵人')
            break

    # ==================== 月德合 ====================
    # 以月支查大运天干，条件：寅午戌见辛，申子辰见丁，巳酉丑见乙，亥卯未见己
    YUANDEHE = {
        ('寅', '午', '戌'): '辛',
        ('申', '子', '辰'): '丁',
        ('巳', '酉', '丑'): '乙',
        ('亥', '卯', '未'): '己',
    }
    for dzs, tg_val in YUANDEHE.items():
        if month_dz in dzs and dayun_tg == tg_val:
            ss.append('月德合')
            break

    # ==================== 文昌贵人 ====================
    # 口诀：甲乙巳午报君知，丙戊申宫丁己鸡，庚猪辛鼠壬逢虎，癸人见卯入云梯
    WENCHANG = {
        '甲': '巳', '乙': '午', '丙': '申', '丁': '酉',
        '戊': '申', '己': '酉', '庚': '亥', '辛': '子',
        '壬': '寅', '癸': '卯',
    }
    if day_tg in WENCHANG and dayun_dz == WENCHANG[day_tg]:
        ss.append('文昌贵人')

    # ==================== 太极贵人 ====================
    # 以年干、日干分开查大运地支
    TAIJI = {
        ('甲', '乙'): ['子', '午'],
        ('丙', '丁'): ['卯', '酉'],
        ('戊', '己'): ['辰', '戌', '丑', '未'],
        ('庚', '辛'): ['寅', '亥'],
        ('壬', '癸'): ['巳', '申'],
    }
    for tgs, dzs in TAIJI.items():
        if (year_tg in tgs or day_tg in tgs) and dayun_dz in dzs:
            ss.append('太极贵人')
            break

    # ==================== 福星贵人 ====================
    # 以年干、日干分开查大运地支
    FUXING = {
        ('甲', '丙'): ['寅', '子'],
        ('乙', '癸'): ['卯', '丑'],
        ('戊',): ['申'],
        ('己',): ['未'],
        ('丁',): ['亥'],
        ('庚',): ['午'],
        ('辛',): ['巳'],
        ('壬',): ['辰'],
    }
    for tgs, dzs in FUXING.items():
        if (year_tg in tgs or day_tg in tgs) and dayun_dz in dzs:
            ss.append('福星贵人')
            break

    # ==================== 德秀贵人 ====================
    # 依据月地支，查年、月、日、时、大运天干组合
    DEXIU = {
        ('寅', '午', '戌'): (set(['丙', '丁']), set(['戊', '癸'])),
        ('申', '子', '辰'): (set(['壬', '癸', '戊', '己']), set(['丙', '辛', '甲', '己'])),
        ('巳', '酉', '丑'): (set(['庚', '辛']), set(['乙', '庚'])),
        ('亥', '卯', '未'): (set(['甲', '乙']), set(['丁', '壬'])),
    }
    for dzs, (set1, set2) in DEXIU.items():
        if month_dz in dzs:
            # 检查大运天干是否在集合中
            if dayun_tg in set1 or dayun_tg in set2:
                ss.append('德秀贵人')
            break

    # ==================== 国印贵人 ====================
    # 以年干、日干分开查大运地支
    GUOYIN = {
        '甲': '戌', '乙': '亥', '丙': '丑', '丁': '寅',
        '戊': '丑', '己': '寅', '庚': '辰', '辛': '巳',
        '壬': '未', '癸': '申',
    }
    # 以年干查大运地支
    if year_tg in GUOYIN and dayun_dz == GUOYIN[year_tg]:
        ss.append('国印贵人')
    # 以日干查大运地支（避免重复添加）
    if day_tg in GUOYIN and dayun_dz == GUOYIN[day_tg] and '国印贵人' not in ss:
        ss.append('国印贵人')

    # ==================== 天厨贵人 ====================
    # 以年干、日干分别查大运地支
    TIANCHU = {
        '甲': '巳', '乙': '午', '丙': '巳', '丁': '午',
        '戊': '申', '己': '酉', '庚': '亥', '辛': '子',
        '壬': '寅', '癸': '卯',
    }
    # 以年干查大运地支
    if year_tg in TIANCHU and dayun_dz == TIANCHU[year_tg]:
        ss.append('天厨贵人')
    # 以日干查大运地支（避免重复添加）
    if day_tg in TIANCHU and dayun_dz == TIANCHU[day_tg] and '天厨贵人' not in ss:
        ss.append('天厨贵人')
    
    # ==================== 咸池 ====================
    # 以年支或日支查大运地支
    XIANCHI_DZS = {
        ('申', '子', '辰'): '酉',
        ('寅', '午', '戌'): '卯',
        ('巳', '酉', '丑'): '午',
        ('亥', '卯', '未'): '子',
    }
    for dzs, target_dz in XIANCHI_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and dayun_dz == target_dz:
            ss.append('咸池')
            break

    # ==================== 纳音桃花 ====================
    # 以年柱纳音五行查大运地支
    # 年柱纳音为金，大运地支见巳或亥为纳音桃花
    # 年柱纳音为木，大运地支见亥或卯为纳音桃花
    # 年柱纳音为火，大运地支见申或子为纳音桃花
    # 年柱纳音为水，大运地支见戌或午为纳音桃花
    # 年柱纳音为土，大运地支见戌或午为纳音桃花
    NAYIN_TAOHUA = {
        '金': ['巳', '亥'],
        '木': ['亥', '卯'],
        '火': ['申', '子'],
        '水': ['戌', '午'],
        '土': ['戌', '午'],
    }
    if year_nayin:
        nayin_wuxing = year_nayin[-1]
        if nayin_wuxing in NAYIN_TAOHUA and dayun_dz in NAYIN_TAOHUA[nayin_wuxing]:
            ss.append('纳音桃花')

    # ==================== 禄神 ====================
    # 以日干查大运地支
    LUSHEN = {
        '甲': '寅', '乙': '卯', '丙': '巳', '丁': '午',
        '戊': '巳', '己': '午', '庚': '申', '辛': '酉',
        '壬': '亥', '癸': '子',
    }
    if day_tg in LUSHEN and dayun_dz == LUSHEN[day_tg]:
        ss.append('禄神')

    # ==================== 天喜红鸾 ====================
    # 以年支查大运地支，天喜、红鸾分别查
    TIANXI = {
        '子': '酉', '丑': '申', '寅': '未', '卯': '午',
        '辰': '巳', '巳': '辰', '午': '卯', '未': '寅',
        '申': '丑', '酉': '子', '戌': '亥', '亥': '戌',
    }
    HONGLUAN = {
        '子': '卯', '丑': '寅', '寅': '丑', '卯': '子',
        '辰': '亥', '巳': '戌', '午': '酉', '未': '申',
        '申': '未', '酉': '午', '戌': '巳', '亥': '辰',
    }
    if year_dz in TIANXI and dayun_dz == TIANXI[year_dz]:
        ss.append('天喜')
    if year_dz in HONGLUAN and dayun_dz == HONGLUAN[year_dz]:
        ss.append('红鸾')

    # ==================== 羊刃 ====================
    # 以日干查大运地支
    YANGREN = {
        '甲': '卯', '乙': '寅', '丙': '午', '丁': '巳',
        '戊': '午', '己': '巳', '庚': '酉', '辛': '申',
        '壬': '子', '癸': '亥',
    }
    if day_tg in YANGREN and dayun_dz == YANGREN[day_tg]:
        ss.append('羊刃')

    # ==================== 飞刃 ====================
    # 以日干查大运地支
    FEIREN = {
        '甲': '酉', '乙': '申', '丙': '子', '丁': '亥',
        '戊': '子', '己': '亥', '庚': '卯', '辛': '寅',
        '壬': '午', '癸': '巳',
    }
    if day_tg in FEIREN and dayun_dz == FEIREN[day_tg]:
        ss.append('飞刃')

    # ==================== 血刃 ====================
    # 以月支查大运地支
    XUEREN = {
        '寅': '丑', '卯': '未', '辰': '寅', '巳': '申',
        '午': '卯', '未': '酉', '申': '辰', '酉': '戌',
        '戌': '巳', '亥': '亥', '子': '午', '丑': '子',
    }
    if month_dz in XUEREN and dayun_dz == XUEREN[month_dz]:
        ss.append('血刃')

    # ==================== 流霞 ====================
    # 以日干查大运地支
    LIUXIA = {
        '甲': '酉', '乙': '戌', '丙': '未', '丁': '申',
        '戊': '巳', '己': '午', '庚': '辰', '辛': '卯',
        '壬': '亥', '癸': '寅',
    }
    if day_tg in LIUXIA and dayun_dz == LIUXIA[day_tg]:
        ss.append('流霞')

    # ==================== 驿马 ====================
    # 以年、日支查大运地支
    YIMA_DZS = {
        ('申', '子', '辰'): '寅',
        ('寅', '午', '戌'): '申',
        ('巳', '酉', '丑'): '亥',
        ('亥', '卯', '未'): '巳',
    }
    for dzs, target_dz in YIMA_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and dayun_dz == target_dz:
            ss.append('驿马')
            break

    # ==================== 孤辰 ====================
    # 以年支查大运地支
    GUCHEN_DZS = {
        ('亥', '子', '丑'): '寅',
        ('寅', '卯', '辰'): '巳',
        ('巳', '午', '未'): '申',
        ('申', '酉', '戌'): '亥',
    }
    for dzs, target_dz in GUCHEN_DZS.items():
        if year_dz in dzs and dayun_dz == target_dz:
            ss.append('孤辰')
            break

    # ==================== 寡宿 ====================
    # 以年支查大运地支
    GUSU_DZS = {
        ('亥', '子', '丑'): '戌',
        ('寅', '卯', '辰'): '丑',
        ('巳', '午', '未'): '辰',
        ('申', '酉', '戌'): '未',
    }
    for dzs, target_dz in GUSU_DZS.items():
        if year_dz in dzs and dayun_dz == target_dz:
            ss.append('寡宿')
            break

    # ==================== 空亡 ====================
    # 以日柱查大运地支，确定日柱所在的六十甲子旬
    GANZHI = [
        '甲子', '乙丑', '丙寅', '丁卯', '戊辰', '己巳', '庚午', '辛未', '壬申', '癸酉',
        '甲戌', '乙亥', '丙子', '丁丑', '戊寅', '己卯', '庚辰', '辛巳', '壬午', '癸未',
        '甲申', '乙酉', '丙戌', '丁亥', '戊子', '己丑', '庚寅', '辛卯', '壬辰', '癸巳',
        '甲午', '乙未', '丙申', '丁酉', '戊戌', '己亥', '庚子', '辛丑', '壬寅', '癸卯',
        '甲辰', '乙巳', '丙午', '丁未', '戊申', '己酉', '庚戌', '辛亥', '壬子', '癸丑',
        '甲寅', '乙卯', '丙辰', '丁巳', '戊午', '己未', '庚申', '辛酉', '壬戌', '癸亥',
    ]
    XUNKONGWANG = {
        0: ['戌', '亥'],  # 甲子旬
        1: ['申', '酉'],  # 甲戌旬
        2: ['午', '未'],  # 甲申旬
        3: ['辰', '巳'],  # 甲午旬
        4: ['寅', '卯'],  # 甲辰旬
        5: ['子', '丑'],  # 甲寅旬
    }
    day_gz = day_tg + day_dz
    day_gz_idx = None
    for i, gz in enumerate(GANZHI):
        if gz == day_gz:
            day_gz_idx = i
            break
    if day_gz_idx is not None:
        xunkun_idx = day_gz_idx // 10
        xunkun_gzs = XUNKONGWANG[xunkun_idx]
        if dayun_dz in xunkun_gzs:
            ss.append('空亡')

    # ==================== 红艳煞 ====================
    # 以日干查大运地支
    HONGYANSHA = {
        '甲': '午', '乙': '午', '丙': '寅', '丁': '未',
        '戊': '辰', '己': '辰', '庚': '戌', '辛': '酉',
        '壬': '子', '癸': '申',
    }
    if day_tg in HONGYANSHA and dayun_dz == HONGYANSHA[day_tg]:
        ss.append('红艳煞')
        
    # ==================== 学堂 ====================
    # 以年柱纳音五行查大运地支，如果满足干支要求则升级为"正学堂"
    # 年柱纳音为金，大运支有"巳"为学堂，额外判断如果大运干支为"辛巳"为正学堂
    # 年柱纳音为木，大运支有"亥"为学堂，额外判断如果大运干支为"己亥"为正学堂
    # 年柱纳音为水，大运支有"申"为学堂，额外判断如果大运干支为"甲申"为正学堂
    # 年柱纳音为土，大运支有"申"为学堂，额外判断如果大运干支为"戊申"为正学堂
    # 年柱纳音为火，大运支有"寅"为学堂，额外判断如果大运干支为"丙寅"为正学堂
    XUETANG = {
        '金': ('巳', '辛巳'),
        '木': ('亥', '己亥'),
        '水': ('申', '甲申'),
        '土': ('申', '戊申'),
        '火': ('寅', '丙寅'),
    }
    if year_nayin:
        nayin_wuxing = year_nayin[-1]
        if nayin_wuxing in XUETANG:
            target_dz, target_gz = XUETANG[nayin_wuxing]
            dayun_gz = dayun_tg + dayun_dz
            if dayun_dz == target_dz:
                if dayun_gz == target_gz:
                    ss.append('正学堂')
                else:
                    ss.append('学堂')

    # ==================== 词馆 ====================
    # 以年柱纳音五行查大运地支，如果满足干支要求则升级为"正词馆"
    # 年柱纳音为金，大运支有"申"为词馆，额外判断如果大运为"壬申"为正词馆
    # 年柱纳音为木，大运支有"寅"为词馆，额外判断如果大运为"庚寅"为正词馆
    # 年柱纳音为水，大运支有"亥"为词馆，额外判断如果大运为"癸亥"为正词馆
    # 年柱纳音为土，大运支有"亥"为词馆，额外判断如果大运为"丁亥"为正词馆
    # 年柱纳音为火，大运支有"巳"为词馆，额外判断如果大运为"乙巳"为正词馆
    CIGUAN = {
        '金': ('申', '壬申'),
        '木': ('寅', '庚寅'),
        '水': ('亥', '癸亥'),
        '土': ('亥', '丁亥'),
        '火': ('巳', '乙巳'),
    }
    if year_nayin:
        nayin_wuxing = year_nayin[-1]
        if nayin_wuxing in CIGUAN:
            target_dz, target_gz = CIGUAN[nayin_wuxing]
            dayun_gz = dayun_tg + dayun_dz
            if dayun_dz == target_dz:
                if dayun_gz == target_gz:
                    ss.append('正词馆')
                else:
                    ss.append('词馆')

    # ==================== 将星 ====================
    # 以年支、日支分开查大运地支
    JIANGXING_DZS = {
        ('申', '子', '辰'): '子',
        ('巳', '酉', '丑'): '酉',
        ('寅', '午', '戌'): '午',
        ('亥', '卯', '未'): '卯',
    }
    for dzs, target_dz in JIANGXING_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and dayun_dz == target_dz:
            ss.append('将星')
            break

    # ==================== 金舆 ====================
    # 以年、日干查大运地支
    JINYU = {
        ('甲',): '辰', ('乙',): '巳',
        ('丙', '戊'): '未', ('丁', '己'): '申',
        ('庚',): '戌', ('辛',): '亥',
        ('壬',): '丑', ('癸',): '寅',
    }
    for tgs, target_dz in JINYU.items():
        if (year_tg in tgs or day_tg in tgs) and dayun_dz == target_dz:
            ss.append('金舆')
            break

    # ==================== 华盖 ====================
    # 以年支和日支分开查大运地支
    HUAGAI_DZS = {
        ('寅', '午', '戌'): '戌',
        ('亥', '卯', '未'): '未',
        ('巳', '酉', '丑'): '丑',
        ('申', '子', '辰'): '辰',
    }
    for dzs, target_dz in HUAGAI_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and dayun_dz == target_dz:
            ss.append('华盖')
            break

    # ==================== 劫煞 ====================
    # 以年支和日支分别查大运地支
    JIESHA_DZS = {
        ('寅', '午', '戌'): '亥',
        ('亥', '卯', '未'): '申',
        ('巳', '酉', '丑'): '寅',
        ('申', '子', '辰'): '巳',
    }
    for dzs, target_dz in JIESHA_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and dayun_dz == target_dz:
            ss.append('劫煞')
            break

    # ==================== 灾煞 ====================
    # 以年支查大运地支
    ZAISHA_DZS = {
        ('寅', '午', '戌'): '子',
        ('亥', '卯', '未'): '酉',
        ('巳', '酉', '丑'): '卯',
        ('申', '子', '辰'): '午',
    }
    for dzs, target_dz in ZAISHA_DZS.items():
        if year_dz in dzs and dayun_dz == target_dz:
            ss.append('灾煞')
            break

    # ==================== 亡神 ====================
    # 以年支和日支分别查大运地支
    WANGSHEN_DZS = {
        ('寅', '午', '戌'): '巳',
        ('亥', '卯', '未'): '寅',
        ('巳', '酉', '丑'): '申',
        ('申', '子', '辰'): '亥',
    }
    for dzs, target_dz in WANGSHEN_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and dayun_dz == target_dz:
            ss.append('亡神')
            break

    # ==================== 丧门吊客披麻 ====================
    # 以年地支查大运地支
    SANGMEN_DIAOKE_PIMA = {
        '子': ('寅', '戌', '酉'),
        '午': ('申', '辰', '卯'),
        '亥': ('丑', '酉', '申'),
    }
    if year_dz in SANGMEN_DIAOKE_PIMA:
        sangmen, diaoke, pima = SANGMEN_DIAOKE_PIMA[year_dz]
        if dayun_dz == sangmen:
            ss.append('丧门')
        if dayun_dz == diaoke:
            ss.append('吊客')
        if dayun_dz == pima:
            ss.append('披麻')


    return ss if ss else ['无']

# ===========流年神煞处理函数=========
def calculate_liunian_shensha(liunian_tg: str, liunian_dz: str,
                              day_tg: str, day_dz: str,
                              year_tg: str, year_dz: str,
                              month_tg: str, month_dz: str,
                              hour_tg: str, hour_dz: str,
                              year_nayin: str = '') -> List[str]:
    """计算流年神煞（将流年干支看作单柱，按照四柱神煞的标准计算）"""
    ss = []

    # ==================== 天乙贵人 ====================
    # 口诀：甲戊庚牛羊, 乙己鼠猴乡, 丙丁猪鸡位, 壬癸兔蛇藏, 六辛逢虎马
    # 以年干、日干分别查流年地支，命中则有天乙贵人
    TIANYI = {
        '甲': ['丑', '未'], '乙': ['子', '申'], '丙': ['亥', '酉'],
        '丁': ['亥', '酉'], '戊': ['丑', '未'], '己': ['子', '申'],
        '庚': ['丑', '未'], '辛': ['寅', '午'], '壬': ['卯', '巳'],
        '癸': ['卯', '巳'],
    }
    # 以年干查流年地支
    if year_tg in TIANYI and liunian_dz in TIANYI[year_tg]:
        ss.append('天乙贵人')
    # 以日干查流年地支（避免重复添加）
    if day_tg in TIANYI and liunian_dz in TIANYI[day_tg] and '天乙贵人' not in ss:
        ss.append('天乙贵人')

    # ==================== 天德贵人 ====================
    # 口诀：寅丁卯申辰壬巳辛，午亥未甲申癸酉寅，戌丙亥乙子巳丑庚
    # 以月支查流年干支（天干和地支都要看），命中则有天德贵人
    TIANDE = {
        '寅': '丁', '卯': '申', '辰': '壬', '巳': '辛',
        '午': '亥', '未': '甲', '申': '癸', '酉': '寅',
        '戌': '丙', '亥': '乙', '子': '巳', '丑': '庚',
    }
    if month_dz in TIANDE:
        tiande_val = TIANDE[month_dz]
        # 流年天干或地支中有对应字符，则命中
        if liunian_tg == tiande_val or liunian_dz == tiande_val:
            ss.append('天德贵人')

    # ==================== 天德合 ====================
    # 以月支查天德合字典，检查流年天干或地支是否包含对应字符
    TIANDEHE = {
        '寅': '壬', '卯': '巳', '辰': '丁', '巳': '丙',
        '午': '寅', '未': '己', '申': '戊', '酉': '亥',
        '戌': '辛', '亥': '庚', '子': '申', '丑': '乙',
    }
    if month_dz in TIANDEHE:
        tiandehe_val = TIANDEHE[month_dz]
        if liunian_tg == tiandehe_val or liunian_dz == tiandehe_val:
            ss.append('天德合')

    # ==================== 月德贵人 ====================
    # 以月支查流年天干，条件：寅午戌见丙，申子辰见壬，亥卯未见甲，巳酉丑见庚
    YUANDE = {
        ('寅', '午', '戌'): '丙',
        ('申', '子', '辰'): '壬',
        ('亥', '卯', '未'): '甲',
        ('巳', '酉', '丑'): '庚',
    }
    for dzs, tg_val in YUANDE.items():
        if month_dz in dzs and liunian_tg == tg_val:
            ss.append('月德贵人')
            break

    # ==================== 月德合 ====================
    # 以月支查流年天干，条件：寅午戌见辛，申子辰见丁，巳酉丑见乙，亥卯未见己
    YUANDEHE = {
        ('寅', '午', '戌'): '辛',
        ('申', '子', '辰'): '丁',
        ('巳', '酉', '丑'): '乙',
        ('亥', '卯', '未'): '己',
    }
    for dzs, tg_val in YUANDEHE.items():
        if month_dz in dzs and liunian_tg == tg_val:
            ss.append('月德合')
            break

    # ==================== 文昌贵人 ====================
    # 口诀：甲乙巳午报君知，丙戊申宫丁己鸡，庚猪辛鼠壬逢虎，癸人见卯入云梯
    WENCHANG = {
        '甲': '巳', '乙': '午', '丙': '申', '丁': '酉',
        '戊': '申', '己': '酉', '庚': '亥', '辛': '子',
        '壬': '寅', '癸': '卯',
    }
    if day_tg in WENCHANG and liunian_dz == WENCHANG[day_tg]:
        ss.append('文昌贵人')

    # ==================== 太极贵人 ====================
    # 以年干、日干分开查流年地支
    TAIJI = {
        ('甲', '乙'): ['子', '午'],
        ('丙', '丁'): ['卯', '酉'],
        ('戊', '己'): ['辰', '戌', '丑', '未'],
        ('庚', '辛'): ['寅', '亥'],
        ('壬', '癸'): ['巳', '申'],
    }
    for tgs, dzs in TAIJI.items():
        if (year_tg in tgs or day_tg in tgs) and liunian_dz in dzs:
            ss.append('太极贵人')
            break

    # ==================== 福星贵人 ====================
    # 以年干、日干分开查流年地支
    FUXING = {
        ('甲', '丙'): ['寅', '子'],
        ('乙', '癸'): ['卯', '丑'],
        ('戊',): ['申'],
        ('己',): ['未'],
        ('丁',): ['亥'],
        ('庚',): ['午'],
        ('辛',): ['巳'],
        ('壬',): ['辰'],
    }
    for tgs, dzs in FUXING.items():
        if (year_tg in tgs or day_tg in tgs) and liunian_dz in dzs:
            ss.append('福星贵人')
            break

    # ==================== 德秀贵人 ====================
    # 依据月地支，查年、月、日、时、流年天干组合
    DEXIU = {
        ('寅', '午', '戌'): (set(['丙', '丁']), set(['戊', '癸'])),
        ('申', '子', '辰'): (set(['壬', '癸', '戊', '己']), set(['丙', '辛', '甲', '己'])),
        ('巳', '酉', '丑'): (set(['庚', '辛']), set(['乙', '庚'])),
        ('亥', '卯', '未'): (set(['甲', '乙']), set(['丁', '壬'])),
    }
    for dzs, (set1, set2) in DEXIU.items():
        if month_dz in dzs:
            # 检查流年天干是否在集合中
            if liunian_tg in set1 or liunian_tg in set2:
                ss.append('德秀贵人')
            break

    # ==================== 国印贵人 ====================
    # 以年干、日干分开查流年地支
    GUOYIN = {
        '甲': '戌', '乙': '亥', '丙': '丑', '丁': '寅',
        '戊': '丑', '己': '寅', '庚': '辰', '辛': '巳',
        '壬': '未', '癸': '申',
    }
    # 以年干查流年地支
    if year_tg in GUOYIN and liunian_dz == GUOYIN[year_tg]:
        ss.append('国印贵人')
    # 以日干查流年地支（避免重复添加）
    if day_tg in GUOYIN and liunian_dz == GUOYIN[day_tg] and '国印贵人' not in ss:
        ss.append('国印贵人')

    # ==================== 天厨贵人 ====================
    # 以年干、日干分别查流年地支
    TIANCHU = {
        '甲': '巳', '乙': '午', '丙': '巳', '丁': '午',
        '戊': '申', '己': '酉', '庚': '亥', '辛': '子',
        '壬': '寅', '癸': '卯',
    }
    # 以年干查流年地支
    if year_tg in TIANCHU and liunian_dz == TIANCHU[year_tg]:
        ss.append('天厨贵人')
    # 以日干查流年地支（避免重复添加）
    if day_tg in TIANCHU and liunian_dz == TIANCHU[day_tg] and '天厨贵人' not in ss:
        ss.append('天厨贵人')

    # ==================== 咸池 ====================
    # 以年支或日支查流年地支
    XIANCHI_DZS = {
        ('申', '子', '辰'): '酉',
        ('寅', '午', '戌'): '卯',
        ('巳', '酉', '丑'): '午',
        ('亥', '卯', '未'): '子',
    }
    for dzs, target_dz in XIANCHI_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and liunian_dz == target_dz:
            ss.append('咸池')
            break

    # ==================== 纳音桃花 ====================
    # 以年柱纳音五行查流年地支
    # 年柱纳音为金，流年地支见巳或亥为纳音桃花
    # 年柱纳音为木，流年地支见亥或卯为纳音桃花
    # 年柱纳音为火，流年地支见申或子为纳音桃花
    # 年柱纳音为水，流年地支见戌或午为纳音桃花
    # 年柱纳音为土，流年地支见戌或午为纳音桃花
    NAYIN_TAOHUA = {
        '金': ['巳', '亥'],
        '木': ['亥', '卯'],
        '火': ['申', '子'],
        '水': ['戌', '午'],
        '土': ['戌', '午'],
    }
    if year_nayin:
        nayin_wuxing = year_nayin[-1]
        if nayin_wuxing in NAYIN_TAOHUA and liunian_dz in NAYIN_TAOHUA[nayin_wuxing]:
            ss.append('纳音桃花')

    # ==================== 禄神 ====================
    # 以日干查流年地支
    LUSHEN = {
        '甲': '寅', '乙': '卯', '丙': '巳', '丁': '午',
        '戊': '巳', '己': '午', '庚': '申', '辛': '酉',
        '壬': '亥', '癸': '子',
    }
    if day_tg in LUSHEN and liunian_dz == LUSHEN[day_tg]:
        ss.append('禄神')

    # ==================== 天喜红鸾 ====================
    # 以年支查流年地支，天喜、红鸾分别查
    TIANXI = {
        '子': '酉', '丑': '申', '寅': '未', '卯': '午',
        '辰': '巳', '巳': '辰', '午': '卯', '未': '寅',
        '申': '丑', '酉': '子', '戌': '亥', '亥': '戌',
    }
    HONGLUAN = {
        '子': '卯', '丑': '寅', '寅': '丑', '卯': '子',
        '辰': '亥', '巳': '戌', '午': '酉', '未': '申',
        '申': '未', '酉': '午', '戌': '巳', '亥': '辰',
    }
    if year_dz in TIANXI and liunian_dz == TIANXI[year_dz]:
        ss.append('天喜')
    if year_dz in HONGLUAN and liunian_dz == HONGLUAN[year_dz]:
        ss.append('红鸾')

    # ==================== 羊刃 ====================
    # 以日干查流年地支
    YANGREN = {
        '甲': '卯', '乙': '寅', '丙': '午', '丁': '巳',
        '戊': '午', '己': '巳', '庚': '酉', '辛': '申',
        '壬': '子', '癸': '亥',
    }
    if day_tg in YANGREN and liunian_dz == YANGREN[day_tg]:
        ss.append('羊刃')

    # ==================== 飞刃 ====================
    # 以日干查流年地支
    FEIREN = {
        '甲': '酉', '乙': '申', '丙': '子', '丁': '亥',
        '戊': '子', '己': '亥', '庚': '卯', '辛': '寅',
        '壬': '午', '癸': '巳',
    }
    if day_tg in FEIREN and liunian_dz == FEIREN[day_tg]:
        ss.append('飞刃')

    # ==================== 血刃 ====================
    # 以月支查流年地支
    XUEREN = {
        '寅': '丑', '卯': '未', '辰': '寅', '巳': '申',
        '午': '卯', '未': '酉', '申': '辰', '酉': '戌',
        '戌': '巳', '亥': '亥', '子': '午', '丑': '子',
    }
    if month_dz in XUEREN and liunian_dz == XUEREN[month_dz]:
        ss.append('血刃')

    # ==================== 流霞 ====================
    # 以日干查流年地支
    LIUXIA = {
        '甲': '酉', '乙': '戌', '丙': '未', '丁': '申',
        '戊': '巳', '己': '午', '庚': '辰', '辛': '卯',
        '壬': '亥', '癸': '寅',
    }
    if day_tg in LIUXIA and liunian_dz == LIUXIA[day_tg]:
        ss.append('流霞')

    # ==================== 驿马 ====================
    # 以年、日支查流年地支
    YIMA_DZS = {
        ('申', '子', '辰'): '寅',
        ('寅', '午', '戌'): '申',
        ('巳', '酉', '丑'): '亥',
        ('亥', '卯', '未'): '巳',
    }
    for dzs, target_dz in YIMA_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and liunian_dz == target_dz:
            ss.append('驿马')
            break

    # ==================== 孤辰 ====================
    # 以年支查流年地支
    GUCHEN_DZS = {
        ('亥', '子', '丑'): '寅',
        ('寅', '卯', '辰'): '巳',
        ('巳', '午', '未'): '申',
        ('申', '酉', '戌'): '亥',
    }
    for dzs, target_dz in GUCHEN_DZS.items():
        if year_dz in dzs and liunian_dz == target_dz:
            ss.append('孤辰')
            break

    # ==================== 寡宿 ====================
    # 以年支查流年地支
    GUSU_DZS = {
        ('亥', '子', '丑'): '戌',
        ('寅', '卯', '辰'): '丑',
        ('巳', '午', '未'): '辰',
        ('申', '酉', '戌'): '未',
    }
    for dzs, target_dz in GUSU_DZS.items():
        if year_dz in dzs and liunian_dz == target_dz:
            ss.append('寡宿')
            break

    # ==================== 空亡 ====================
    # 以日柱查流年地支，确定日柱所在的六十甲子旬
    GANZHI = [
        '甲子', '乙丑', '丙寅', '丁卯', '戊辰', '己巳', '庚午', '辛未', '壬申', '癸酉',
        '甲戌', '乙亥', '丙子', '丁丑', '戊寅', '己卯', '庚辰', '辛巳', '壬午', '癸未',
        '甲申', '乙酉', '丙戌', '丁亥', '戊子', '己丑', '庚寅', '辛卯', '壬辰', '癸巳',
        '甲午', '乙未', '丙申', '丁酉', '戊戌', '己亥', '庚子', '辛丑', '壬寅', '癸卯',
        '甲辰', '乙巳', '丙午', '丁未', '戊申', '己酉', '庚戌', '辛亥', '壬子', '癸丑',
        '甲寅', '乙卯', '丙辰', '丁巳', '戊午', '己未', '庚申', '辛酉', '壬戌', '癸亥',
    ]
    XUNKONGWANG = {
        0: ['戌', '亥'],  # 甲子旬
        1: ['申', '酉'],  # 甲戌旬
        2: ['午', '未'],  # 甲申旬
        3: ['辰', '巳'],  # 甲午旬
        4: ['寅', '卯'],  # 甲辰旬
        5: ['子', '丑'],  # 甲寅旬
    }
    day_gz = day_tg + day_dz
    day_gz_idx = None
    for i, gz in enumerate(GANZHI):
        if gz == day_gz:
            day_gz_idx = i
            break
    if day_gz_idx is not None:
        xunkun_idx = day_gz_idx // 10
        xunkun_gzs = XUNKONGWANG[xunkun_idx]
        if liunian_dz in xunkun_gzs:
            ss.append('空亡')

    # ==================== 红艳煞 ====================
    # 以日干查流年地支
    HONGYANSHA = {
        '甲': '午', '乙': '午', '丙': '寅', '丁': '未',
        '戊': '辰', '己': '辰', '庚': '戌', '辛': '酉',
        '壬': '子', '癸': '申',
    }
    if day_tg in HONGYANSHA and liunian_dz == HONGYANSHA[day_tg]:
        ss.append('红艳煞')

    # ==================== 学堂 ====================
    # 以年柱纳音五行查流年地支，如果满足干支要求则升级为"正学堂"
    # 年柱纳音为金，流年支有"巳"为学堂，额外判断如果流年干支为"辛巳"为正学堂
    # 年柱纳音为木，流年支有"亥"为学堂，额外判断如果流年干支为"己亥"为正学堂
    # 年柱纳音为水，流年支有"申"为学堂，额外判断如果流年干支为"甲申"为正学堂
    # 年柱纳音为土，流年支有"申"为学堂，额外判断如果流年干支为"戊申"为正学堂
    # 年柱纳音为火，流年支有"寅"为学堂，额外判断如果流年干支为"丙寅"为正学堂
    XUETANG = {
        '金': ('巳', '辛巳'),
        '木': ('亥', '己亥'),
        '水': ('申', '甲申'),
        '土': ('申', '戊申'),
        '火': ('寅', '丙寅'),
    }
    if year_nayin:
        nayin_wuxing = year_nayin[-1]
        if nayin_wuxing in XUETANG:
            target_dz, target_gz = XUETANG[nayin_wuxing]
            liunian_gz = liunian_tg + liunian_dz
            if liunian_dz == target_dz:
                if liunian_gz == target_gz:
                    ss.append('正学堂')
                else:
                    ss.append('学堂')

    # ==================== 词馆 ====================
    # 以年柱纳音五行查流年地支，如果满足干支要求则升级为"正词馆"
    # 年柱纳音为金，流年支有"申"为词馆，额外判断如果流年为"壬申"为正词馆
    # 年柱纳音为木，流年支有"寅"为词馆，额外判断如果流年为"庚寅"为正词馆
    # 年柱纳音为水，流年支有"亥"为词馆，额外判断如果流年为"癸亥"为正词馆
    # 年柱纳音为土，流年支有"亥"为词馆，额外判断如果流年为"丁亥"为正词馆
    # 年柱纳音为火，流年支有"巳"为词馆，额外判断如果流年为"乙巳"为正词馆
    CIGUAN = {
        '金': ('申', '壬申'),
        '木': ('寅', '庚寅'),
        '水': ('亥', '癸亥'),
        '土': ('亥', '丁亥'),
        '火': ('巳', '乙巳'),
    }
    if year_nayin:
        nayin_wuxing = year_nayin[-1]
        if nayin_wuxing in CIGUAN:
            target_dz, target_gz = CIGUAN[nayin_wuxing]
            liunian_gz = liunian_tg + liunian_dz
            if liunian_dz == target_dz:
                if liunian_gz == target_gz:
                    ss.append('正词馆')
                else:
                    ss.append('词馆')

    # ==================== 将星 ====================
    # 以年支、日支分开查流年地支
    JIANGXING_DZS = {
        ('申', '子', '辰'): '子',
        ('巳', '酉', '丑'): '酉',
        ('寅', '午', '戌'): '午',
        ('亥', '卯', '未'): '卯',
    }
    for dzs, target_dz in JIANGXING_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and liunian_dz == target_dz:
            ss.append('将星')
            break

    # ==================== 金舆 ====================
    # 以年、日干查流年地支
    JINYU = {
        ('甲',): '辰', ('乙',): '巳',
        ('丙', '戊'): '未', ('丁', '己'): '申',
        ('庚',): '戌', ('辛',): '亥',
        ('壬',): '丑', ('癸',): '寅',
    }
    for tgs, target_dz in JINYU.items():
        if (year_tg in tgs or day_tg in tgs) and liunian_dz == target_dz:
            ss.append('金舆')
            break

    # ==================== 华盖 ====================
    # 以年支和日支分开查流年地支
    HUAGAI_DZS = {
        ('寅', '午', '戌'): '戌',
        ('亥', '卯', '未'): '未',
        ('巳', '酉', '丑'): '丑',
        ('申', '子', '辰'): '辰',
    }
    for dzs, target_dz in HUAGAI_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and liunian_dz == target_dz:
            ss.append('华盖')
            break

    # ==================== 劫煞 ====================
    # 以年支和日支分别查流年地支
    JIESHA_DZS = {
        ('寅', '午', '戌'): '亥',
        ('亥', '卯', '未'): '申',
        ('巳', '酉', '丑'): '寅',
        ('申', '子', '辰'): '巳',
    }
    for dzs, target_dz in JIESHA_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and liunian_dz == target_dz:
            ss.append('劫煞')
            break

    # ==================== 灾煞 ====================
    # 以年支查流年地支
    ZAISHA_DZS = {
        ('寅', '午', '戌'): '子',
        ('亥', '卯', '未'): '酉',
        ('巳', '酉', '丑'): '卯',
        ('申', '子', '辰'): '午',
    }
    for dzs, target_dz in ZAISHA_DZS.items():
        if year_dz in dzs and liunian_dz == target_dz:
            ss.append('灾煞')
            break

    # ==================== 亡神 ====================
    # 以年支和日支分别查流年地支
    WANGSHEN_DZS = {
        ('寅', '午', '戌'): '巳',
        ('亥', '卯', '未'): '寅',
        ('巳', '酉', '丑'): '申',
        ('申', '子', '辰'): '亥',
    }
    for dzs, target_dz in WANGSHEN_DZS.items():
        if (year_dz in dzs or day_dz in dzs) and liunian_dz == target_dz:
            ss.append('亡神')
            break

    # ==================== 丧门吊客披麻 ====================
    # 以年地支查流年地支
    SANGMEN_DIAOKE_PIMA = {
        '子': ('寅', '戌', '酉'),
        '午': ('申', '辰', '卯'),
        '亥': ('丑', '酉', '申'),
    }
    if year_dz in SANGMEN_DIAOKE_PIMA:
        sangmen, diaoke, pima = SANGMEN_DIAOKE_PIMA[year_dz]
        if liunian_dz == sangmen:
            ss.append('丧门')
        if liunian_dz == diaoke:
            ss.append('吊客')
        if liunian_dz == pima:
            ss.append('披麻')

    return ss if ss else ['无']


def calculate_dayun_xingchong(dayun_tg: str, dayun_dz: str,
                                 year_tg: str, year_dz: str,
                                 month_tg: str, month_dz: str,
                                 day_tg: str, day_dz: str,
                                 hour_tg: str, hour_dz: str) -> Dict:
    """计算大运与四柱的刑冲合害（大运与年、月、日、时的关系）"""
    all_dz = [year_dz, month_dz, day_dz, hour_dz]
    all_tg = [year_tg, month_tg, day_tg, hour_tg]

    # 天干五合化神
    TIANGAN_HE_WX = {
        ('甲', '己'): '土', ('己', '甲'): '土',
        ('乙', '庚'): '金', ('庚', '乙'): '金',
        ('丙', '辛'): '水', ('辛', '丙'): '水',
        ('丁', '壬'): '木', ('壬', '丁'): '木',
        ('戊', '癸'): '火', ('癸', '戊'): '火',
    }
    DIZHI_LIUHE_WX = {
        ('子', '丑'): '土', ('丑', '子'): '土',
        ('寅', '亥'): '木', ('亥', '寅'): '木',
        ('卯', '戌'): '火', ('戌', '卯'): '火',
        ('辰', '酉'): '金', ('酉', '辰'): '金',
        ('巳', '申'): '水', ('申', '巳'): '水',
        ('午', '未'): '火土', ('未', '午'): '火土',
    }
    SANHE_GROUPS = [
        (['申', '子', '辰'], '水局'),
        (['巳', '酉', '丑'], '金局'),
        (['寅', '午', '戌'], '火局'),
        (['亥', '卯', '未'], '木局'),
    ]
    BANHE_PAIRS = {
        ('申', '子'): '申子半合', ('子', '辰'): '子辰半合', ('申', '辰'): '申辰拱合',
        ('巳', '酉'): '巳酉半合', ('酉', '丑'): '酉丑半合', ('巳', '丑'): '巳丑拱合',
        ('寅', '午'): '寅午半合', ('午', '戌'): '午戌半合', ('寅', '戌'): '寅戌拱合',
        ('亥', '卯'): '亥卯半合', ('卯', '未'): '卯未半合', ('亥', '未'): '亥未拱合',
    }
    ANHE_PAIRS = [
        ('寅', '丑'), ('卯', '申'), ('午', '亥'),
        ('子', '巳'), ('寅', '午'), ('巳', '酉'),
    ]

    result = {}

    # 天干五合（大运天干与四柱天干），格式：大运甲合年干己（甲己合土）
    he = []
    if dayun_tg in TIANGAN_HE:
        he_tg = TIANGAN_HE[dayun_tg]
        for i, tg in enumerate(all_tg):
            if tg == he_tg:
                wx = TIANGAN_HE_WX.get((dayun_tg, tg), '')
                he.append(f"{dayun_tg}{tg}合{wx}")
    result['天干五合'] = he if he else ['无']

    # 地支六合（大运地支与四柱地支）
    liuhe = []
    if dayun_dz in DIZHI_LIUHE:
        he_dz = DIZHI_LIUHE[dayun_dz]
        for i, dz in enumerate(all_dz):
            if dz == he_dz:
                wx = DIZHI_LIUHE_WX.get((dayun_dz, dz), '')
                liuhe.append(f"{dayun_dz}{dz}合{wx}")
    result['地支六合'] = liuhe if liuhe else ['无']

    # 三合/半合（大运地支与四柱地支）
    sanhe = []
    for group, ju_name in SANHE_GROUPS:
        if dayun_dz in group:
            others = [d for d in group if d != dayun_dz]
            present_others = [d for d in others if d in all_dz]
            if len(present_others) == 2:
                sanhe.append(f"{''.join(group)}三合{ju_name}")
            elif len(present_others) == 1:
                other = present_others[0]
                pair = tuple(sorted([dayun_dz, other]))
                label = BANHE_PAIRS.get(pair, BANHE_PAIRS.get((pair[1], pair[0]), f"{dayun_dz}{other}半合"))
                sanhe.append(label)
    result['地支三合'] = sanhe if sanhe else ['无']

    # 暗合（固定对照表）
    anhe = []
    for a, b in ANHE_PAIRS:
        if (dayun_dz == a and b in all_dz):
            anhe.append(f"{a}{b}暗合")
        elif (dayun_dz == b and a in all_dz):
            anhe.append(f"{b}{a}暗合")
    result['地支暗合'] = anhe if anhe else ['无']

    # 地支六冲（大运地支冲四柱地支）
    chong = []
    if dayun_dz in DIZHI_LIUCHONG:
        chong_dz = DIZHI_LIUCHONG[dayun_dz]
        if chong_dz in all_dz:
            chong.append(f"{dayun_dz}{chong_dz}冲")
    result['地支六冲'] = chong if chong else ['无']

    # 地支相刑（大运地支与四柱地支）
    xing = []
    WUEN_GROUP = ['寅', '巳', '申']
    SHISHI_GROUP = ['丑', '未', '戌']
    if dayun_dz in WUEN_GROUP:
        others = [d for d in WUEN_GROUP if d != dayun_dz]
        for other in others:
            if other in all_dz:
                xing.append(f"{''.join(sorted([dayun_dz, other]))}无恩刑")
    if dayun_dz in SHISHI_GROUP:
        others = [d for d in SHISHI_GROUP if d != dayun_dz]
        for other in others:
            if other in all_dz:
                xing.append(f"{''.join(sorted([dayun_dz, other]))}恃势刑")
    if dayun_dz == '子' and '卯' in all_dz:
        xing.append("子卯无礼刑")
    if dayun_dz == '卯' and '子' in all_dz:
        xing.append("子卯无礼刑")
    if dayun_dz in DIZHI_ZIXING and dayun_dz in all_dz:
        count = all_dz.count(dayun_dz)
        if count >= 2:
            xing.append(f"{dayun_dz * count}自刑")
    result['地支相刑'] = xing if xing else ['无']

    # 六害
    hai = []
    if dayun_dz in DIZHI_LIUHAI:
        hai_dz = DIZHI_LIUHAI[dayun_dz]
        if hai_dz in all_dz:
            hai.append(f"{dayun_dz}{hai_dz}害")
    result['地支六害'] = hai if hai else ['无']

    # 破
    po = []
    if dayun_dz in DIZHI_PO:
        po_dz = DIZHI_PO[dayun_dz]
        if po_dz in all_dz:
            po.append(f"{dayun_dz}{po_dz}破")
    result['地支相破'] = po if po else ['无']

    return result


def calculate_liunian_xingchong(liunian_tg: str, liunian_dz: str,
                                 year_tg: str, year_dz: str,
                                 month_tg: str, month_dz: str,
                                 day_tg: str, day_dz: str,
                                 hour_tg: str, hour_dz: str) -> Dict:
    """计算流年与四柱的刑冲合害（使用与四柱相同的规则）"""
    all_dz = [year_dz, month_dz, day_dz, hour_dz]
    all_tg = [year_tg, month_tg, day_tg, hour_tg]
    pos_names = ['年支', '月支', '日支', '时支']
    tg_pos_names = ['年干', '月干', '日干', '时干']

    # 天干五合化神
    TIANGAN_HE_WX = {
        ('甲', '己'): '土', ('己', '甲'): '土',
        ('乙', '庚'): '金', ('庚', '乙'): '金',
        ('丙', '辛'): '水', ('辛', '丙'): '水',
        ('丁', '壬'): '木', ('壬', '丁'): '木',
        ('戊', '癸'): '火', ('癸', '戊'): '火',
    }
    DIZHI_LIUHE_WX = {
        ('子', '丑'): '土', ('丑', '子'): '土',
        ('寅', '亥'): '木', ('亥', '寅'): '木',
        ('卯', '戌'): '火', ('戌', '卯'): '火',
        ('辰', '酉'): '金', ('酉', '辰'): '金',
        ('巳', '申'): '水', ('申', '巳'): '水',
        ('午', '未'): '火土', ('未', '午'): '火土',
    }
    SANHE_GROUPS = [
        (['申', '子', '辰'], '水局'),
        (['巳', '酉', '丑'], '金局'),
        (['寅', '午', '戌'], '火局'),
        (['亥', '卯', '未'], '木局'),
    ]
    BANHE_PAIRS = {
        ('申', '子'): '申子半合', ('子', '辰'): '子辰半合', ('申', '辰'): '申辰拱合',
        ('巳', '酉'): '巳酉半合', ('酉', '丑'): '酉丑半合', ('巳', '丑'): '巳丑拱合',
        ('寅', '午'): '寅午半合', ('午', '戌'): '午戌半合', ('寅', '戌'): '寅戌拱合',
        ('亥', '卯'): '亥卯半合', ('卯', '未'): '卯未半合', ('亥', '未'): '亥未拱合',
    }
    ANHE_PAIRS = [
        ('寅', '丑'), ('卯', '申'), ('午', '亥'),
        ('子', '巳'), ('寅', '午'), ('巳', '酉'),
    ]

    result = {}

    # 天干五合（流年天干与四柱天干），格式：流年甲合年干己（甲己合土）
    he = []
    if liunian_tg in TIANGAN_HE:
        he_tg = TIANGAN_HE[liunian_tg]
        for i, tg in enumerate(all_tg):
            if tg == he_tg:
                wx = TIANGAN_HE_WX.get((liunian_tg, tg), '')
                he.append(f"{liunian_tg}{tg}合{wx}")
    result['天干五合'] = he if he else ['无']

    # 地支六合（流年地支与四柱地支）
    liuhe = []
    if liunian_dz in DIZHI_LIUHE:
        he_dz = DIZHI_LIUHE[liunian_dz]
        for i, dz in enumerate(all_dz):
            if dz == he_dz:
                wx = DIZHI_LIUHE_WX.get((liunian_dz, dz), '')
                liuhe.append(f"{liunian_dz}{dz}合{wx}")
    result['地支六合'] = liuhe if liuhe else ['无']

    # 三合/半合（流年地支与四柱地支）
    sanhe = []
    for group, ju_name in SANHE_GROUPS:
        if liunian_dz in group:
            others = [d for d in group if d != liunian_dz]
            present_others = [d for d in others if d in all_dz]
            if len(present_others) == 2:
                sanhe.append(f"{''.join(group)}三合{ju_name}")
            elif len(present_others) == 1:
                other = present_others[0]
                pair = tuple(sorted([liunian_dz, other]))
                label = BANHE_PAIRS.get(pair, BANHE_PAIRS.get((pair[1], pair[0]), f"{liunian_dz}{other}半合"))
                sanhe.append(label)
    result['地支三合'] = sanhe if sanhe else ['无']

    # 暗合（固定对照表）
    anhe = []
    for a, b in ANHE_PAIRS:
        if (liunian_dz == a and b in all_dz):
            anhe.append(f"{a}{b}暗合")
        elif (liunian_dz == b and a in all_dz):
            anhe.append(f"{b}{a}暗合")
    result['地支暗合'] = anhe if anhe else ['无']

    # 地支六冲（流年地支冲四柱地支）
    chong = []
    if liunian_dz in DIZHI_LIUCHONG:
        chong_dz = DIZHI_LIUCHONG[liunian_dz]
        if chong_dz in all_dz:
            chong.append(f"{liunian_dz}{chong_dz}冲")
    result['地支六冲'] = chong if chong else ['无']

    # 地支相刑（流年地支与四柱地支）
    xing = []
    WUEN_GROUP = ['寅', '巳', '申']
    SHISHI_GROUP = ['丑', '未', '戌']
    if liunian_dz in WUEN_GROUP:
        others = [d for d in WUEN_GROUP if d != liunian_dz]
        for other in others:
            if other in all_dz:
                xing.append(f"{''.join(sorted([liunian_dz, other]))}无恩刑")
    if liunian_dz in SHISHI_GROUP:
        others = [d for d in SHISHI_GROUP if d != liunian_dz]
        for other in others:
            if other in all_dz:
                xing.append(f"{''.join(sorted([liunian_dz, other]))}恃势刑")
    if liunian_dz == '子' and '卯' in all_dz:
        xing.append("子卯无礼刑")
    if liunian_dz == '卯' and '子' in all_dz:
        xing.append("子卯无礼刑")
    if liunian_dz in DIZHI_ZIXING and liunian_dz in all_dz:
        count = all_dz.count(liunian_dz)
        if count >= 2:
            xing.append(f"{liunian_dz * count}自刑")
    result['地支相刑'] = xing if xing else ['无']

    # 六害
    hai = []
    if liunian_dz in DIZHI_LIUHAI:
        hai_dz = DIZHI_LIUHAI[liunian_dz]
        if hai_dz in all_dz:
            hai.append(f"{liunian_dz}{hai_dz}害")
    result['地支六害'] = hai if hai else ['无']

    # 破
    po = []
    if liunian_dz in DIZHI_PO:
        po_dz = DIZHI_PO[liunian_dz]
        if po_dz in all_dz:
            po.append(f"{liunian_dz}{po_dz}破")
    result['地支相破'] = po if po else ['无']

    return result


# ============================================================
# 第五模块：大运推算（含十神）
# ============================================================

def ganzhi_index_to_pair(idx: int):
    """将60甲子序号（0-59）转为天干地支索引"""
    idx = idx % 60
    tg = idx % 10
    dz = idx % 12
    return tg, dz


def ganzhi_pair_to_index(tg_idx: int, dz_idx: int) -> int:
    """将天干索引(0-9)和地支索引(0-11)转回60甲子序号（0-59）"""
    # 60甲子中，满足 tg_idx%10==tg 且 dz_idx%12==dz 的最小非负整数
    for i in range(60):
        if i % 10 == tg_idx % 10 and i % 12 == dz_idx % 12:
            return i
    return 0


def get_dayun(
    birth_dt_true: datetime,
    year_tg: int,
    month_index: int,
    gender: str,
    solar_terms: List[Tuple[str, datetime]],
    day_tg: str
) -> List[Dict]:
    """计算大运（含天干十神-地支主气十神）"""
    is_yang_year = (year_tg % 2 == 0)
    forward = is_yang_year if gender == '男' else not is_yang_year

    jie_names = set(MONTH_START_TERMS)
    jie_list = [(term_name, dt) for term_name, dt in solar_terms if term_name in jie_names]

    prev_jie, next_jie = None, None
    for term_name, dt in jie_list:
        if dt <= birth_dt_true:
            prev_jie = (term_name, dt)
        elif next_jie is None and dt > birth_dt_true:
            next_jie = (term_name, dt)
            break

    if forward:
        if next_jie is None:
            return []
        ref_dt = next_jie[1]
        days_diff = (ref_dt - birth_dt_true).total_seconds() / 86400
    else:
        if prev_jie is None:
            return []
        ref_dt = prev_jie[1]
        days_diff = (birth_dt_true - ref_dt).total_seconds() / 86400

    qi_yun_years = days_diff / 3.0
    qi_yun_year_int = int(qi_yun_years)
    qi_yun_month_frac = (qi_yun_years - qi_yun_year_int) * 12
    qi_yun_month_int = int(qi_yun_month_frac)
    qi_yun_day_frac = (qi_yun_month_frac - qi_yun_month_int) * 30
    qi_yun_day_int = int(qi_yun_day_frac)

    result = []
    birth_year = birth_dt_true.year

    # 计算出生月柱的60甲子序号
    month_tg_base = [2, 4, 6, 8, 0]
    base_tg = month_tg_base[year_tg % 5]
    birth_month_tg_idx = (base_tg + month_index - 1) % 10
    birth_month_dz_idx = (month_index + 1) % 12
    birth_month_60 = ganzhi_pair_to_index(birth_month_tg_idx, birth_month_dz_idx)

    for i in range(1, 11):
        if forward:
            dayun_60 = (birth_month_60 + i) % 60
        else:
            dayun_60 = (birth_month_60 - i) % 60

        dy_tg_idx, dy_dz_idx = ganzhi_index_to_pair(dayun_60)
        dy_tg_str = TIANGAN[dy_tg_idx]
        dy_dz_str = DIZHI[dy_dz_idx]

        # 大运十神
        dy_shishen_tg = get_shishen_tiangan(day_tg, dy_tg_str)
        cg_main, _, _ = get_canggan_list(dy_dz_str)
        dy_shishen_dz_main = get_shishen_tiangan(day_tg, cg_main) if cg_main else ''

        start_age = qi_yun_year_int + (i - 1) * 10
        start_year = birth_year + start_age

        result.append({
            '运序': i,
            '天干': dy_tg_str,
            '地支': dy_dz_str,
            '干支': dy_tg_str + dy_dz_str,
            '天干十神': dy_shishen_tg,
            '地支主气十神': dy_shishen_dz_main,
            '起运年龄': start_age,
            '起运年份': start_year,
        })

    return result, qi_yun_year_int, qi_yun_month_int, qi_yun_day_int


# ============================================================
# 第六模块：主计算流程
# ============================================================

def parse_location(location_str: str) -> Tuple[float, float]:
    """解析出生地，返回（经度, 纬度）"""
    if ',' in location_str or '，' in location_str:
        parts = location_str.replace('，', ',').split(',')
        if len(parts) == 2:
            try:
                lon = float(parts[0].strip())
                lat = float(parts[1].strip())
                return lon, lat
            except ValueError:
                pass
    for city, (lon, lat) in CITY_DATABASE.items():
        if city in location_str or location_str in city:
            return lon, lat
    print(f"[未找到城市] '{location_str}'，使用北京坐标（116.41°E, 39.90°N）")
    return 116.4074, 39.9042


def calculate_bazi(
    birth_time_str: str,
    location: str,
    gender: str,
    name: str = '',
    liunian: str = None,
    timezone_offset: float = 8.0
) -> Dict:
    """八字排盘主函数（完整版 v2.0）"""
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M'):
        try:
            birth_dt = datetime.strptime(birth_time_str, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"无法解析时间格式：{birth_time_str}，请使用 YYYY-MM-DD HH:MM")

    longitude, latitude = parse_location(location)
    birth_dt_true = local_to_true_solar_time(birth_dt, longitude, timezone_offset)

    # 节气前后各半年
    half_year_days = 365.25 // 2
    solar_terms = get_solar_terms_for_range(birth_dt.year, birth_dt.year + 1)

    # 确定年柱（以立春为界）
    lichun_this_year = None
    lichun_next_year = None
    for term_name, dt in solar_terms:
        if term_name == '立春' and dt.year == birth_dt_true.year:
            lichun_this_year = dt
        if term_name == '立春' and dt.year == birth_dt_true.year + 1:
            lichun_next_year = dt

    year_for_ganzhi = birth_dt_true.year - 1 if lichun_this_year and birth_dt_true < lichun_this_year else birth_dt_true.year
    year_tg_idx, year_dz_idx, year_gz = get_year_ganzhi(year_for_ganzhi)
    year_tg = TIANGAN[year_tg_idx]
    year_dz = DIZHI[year_dz_idx]

    # 确定月柱（以节为界）
    jie_names = set(MONTH_START_TERMS)
    jie_list = [(term_name, dt) for term_name, dt in solar_terms if term_name in jie_names]
    current_jie = None
    for term_name, dt in reversed(jie_list):
        if dt <= birth_dt_true:
            current_jie = (term_name, dt)
            break

    month_index = MONTH_START_TERMS.index(current_jie[0]) + 1 if current_jie else 1
    month_tg_idx, month_dz_idx, month_gz = get_month_ganzhi(year_tg_idx, month_index)
    month_tg = TIANGAN[month_tg_idx]
    month_dz = DIZHI[month_dz_idx]

    # 日柱
    day_tg_idx, day_dz_idx, day_gz = get_day_ganzhi(
        birth_dt_true.year, birth_dt_true.month, birth_dt_true.day
    )
    day_tg = TIANGAN[day_tg_idx]
    day_dz = DIZHI[day_dz_idx]

    # 时柱（需要考虑早子时和晚子时）
    true_hour = birth_dt_true.hour + birth_dt_true.minute / 60.0 + birth_dt_true.second / 3600.0
    hour_day_tg_idx = day_tg_idx  # 默认用当天日柱推算时柱

    # 判断是否为晚子时（23:00-24:00）
    if 23 <= true_hour < 24:
        # 晚子时：需要用后一天日柱推算时柱
        next_day_dt = birth_dt_true + timedelta(days=1)
        next_day_tg_idx, next_day_dz_idx, _ = get_day_ganzhi(
            next_day_dt.year, next_day_dt.month, next_day_dt.day
        )
        hour_day_tg_idx = next_day_tg_idx  # 使用后一天日柱的索引

    hour_tg_idx, hour_dz_idx, hour_gz = get_hour_ganzhi(hour_day_tg_idx, true_hour)
    hour_tg = TIANGAN[hour_tg_idx]
    hour_dz = DIZHI[hour_dz_idx]

    # 藏干
    year_canggan = get_canggan_list(year_dz)
    month_canggan = get_canggan_list(month_dz)
    day_canggan = get_canggan_list(day_dz)
    hour_canggan = get_canggan_list(hour_dz)

    # 十神
    year_tg_shishen = get_shishen_tiangan(day_tg, year_tg)
    month_tg_shishen = get_shishen_tiangan(day_tg, month_tg)
    day_tg_shishen = get_shishen_tiangan(day_tg, day_tg)
    hour_tg_shishen = get_shishen_tiangan(day_tg, hour_tg)

    year_cg_shishen = get_shishen_canggan(day_tg, year_dz)
    month_cg_shishen = get_shishen_canggan(day_tg, month_dz)
    day_cg_shishen = get_shishen_canggan(day_tg, day_dz)
    hour_cg_shishen = get_shishen_canggan(day_tg, hour_dz)

    # 十二长生
    year_changsheng = get_changsheng(day_tg, year_dz)
    month_changsheng = get_changsheng(day_tg, month_dz)
    day_changsheng = get_changsheng(day_tg, day_dz)
    hour_changsheng = get_changsheng(day_tg, hour_dz)

    # 十二长生自坐
    year_zizuo = get_zizuo(year_tg, year_dz)
    month_zizuo = get_zizuo(month_tg, month_dz)
    day_zizuo = get_zizuo(day_tg, day_dz)
    hour_zizuo = get_zizuo(hour_tg, hour_dz)

    # 空亡计算（各柱独立计算，使用数字索引）
    year_kongwang = get_kongwang(year_tg_idx, year_dz_idx, year_dz)
    month_kongwang = get_kongwang(month_tg_idx, month_dz_idx, month_dz)
    day_kongwang = get_kongwang(day_tg_idx, day_dz_idx, day_dz)
    hour_kongwang = get_kongwang(hour_tg_idx, hour_dz_idx, hour_dz)

    # 纳音（使用数字索引）
    year_nayin = get_nayin(year_tg, year_dz)
    month_nayin = get_nayin(month_tg, month_dz)
    day_nayin = get_nayin(day_tg, day_dz)
    hour_nayin = get_nayin(hour_tg, hour_dz)

    # 五行统计
    wuxing_stats = analyze_wuxing_count(year_tg, year_dz, month_tg, month_dz, day_tg, day_dz, hour_tg, hour_dz)

    # 刑冲合害
    xingchonghe = analyze_xingchongheha(year_tg, year_dz, month_tg, month_dz, day_tg, day_dz, hour_tg, hour_dz)

    # 四柱神煞
    shensha_sizhu = calculate_shensha(year_tg, year_dz, month_tg, month_dz, day_tg, day_dz, hour_tg, hour_dz, year_nayin, day_kongwang)

    # 大运
    dayun_result = get_dayun(birth_dt_true, year_tg_idx, month_index, gender, solar_terms, day_tg)
    if isinstance(dayun_result, tuple):
        dayun_list, qi_yun_y, qi_yun_m, qi_yun_d = dayun_result
        # 大运神煞按每步大运分别列出
        dayun_with_shensha = []
        for dy in dayun_list:
            dy_ss = calculate_dayun_shensha(
                dy['天干'], dy['地支'], day_tg, day_dz,
                year_tg, year_dz, month_tg, month_dz, hour_tg, hour_dz, year_nayin
            )
            dy_xc = calculate_dayun_xingchong(
                dy['天干'], dy['地支'],
                year_tg, year_dz, month_tg, month_dz, day_tg, day_dz, hour_tg, hour_dz
            )
            dayun_with_shensha.append({**dy, '神煞': dy_ss, '刑冲合害': dy_xc})
    else:
        dayun_with_shensha, qi_yun_y, qi_yun_m, qi_yun_d = dayun_result, 0, 0, 0

    # 流年（当前年份，而非出生年份）
    # 如果指定了流年年份，使用指定年份；否则使用当前年份
    if liunian:
        liunian_year = int(liunian)
        # 确定流年干支（以立春为界，使用当年的立春时间判断）
        liunian_solar_terms = get_solar_terms_for_range(liunian_year, liunian_year + 1)
        lichun_liunian = None
        for term_name, dt in liunian_solar_terms:
            if term_name == '立春' and dt.year == liunian_year:
                lichun_liunian = dt
                break
        # 流年以立春为界确定干支
        now_for_liunian = datetime.now()
        liunian_year_for_gz = liunian_year - 1 if lichun_liunian and now_for_liunian < lichun_liunian else liunian_year
    else:
        now = datetime.now()
        liunian_year = now.year
        # 确定当前年的干支（以立春为界）
        current_solar_terms = get_solar_terms_for_range(liunian_year, liunian_year + 1)
        lichun_current = None
        for term_name, dt in current_solar_terms:
            if term_name == '立春' and dt.year == liunian_year:
                lichun_current = dt
                break
        liunian_year_for_gz = liunian_year - 1 if lichun_current and now < lichun_current else liunian_year
    ln_tg_idx, ln_dz_idx, ln_gz = get_year_ganzhi(liunian_year_for_gz)
    liunian_tg_ln = TIANGAN[ln_tg_idx]
    liunian_dz_ln = DIZHI[ln_dz_idx]
    liunian_shensha = calculate_liunian_shensha(
        liunian_tg_ln, liunian_dz_ln,
        day_tg, day_dz,
        year_tg, year_dz, month_tg, month_dz,
        hour_tg, hour_dz, year_nayin
    )
    liunian_xingchong = calculate_liunian_xingchong(
        liunian_tg_ln, liunian_dz_ln,
        year_tg, year_dz, month_tg, month_dz,
        day_tg, day_dz, hour_tg, hour_dz
    )

    # 节气描述（修正前后逻辑：节气日期 > 出生日期 → 节气在后 → 出生在节气之前）
    birth_jie_desc = []
    for term_name, dt in solar_terms:
        diff_days = (dt - birth_dt_true).total_seconds() / 86400
        if abs(diff_days) <= half_year_days:
            if diff_days > 0:
                # 节气日期晚于出生，出生在节气之前
                birth_jie_desc.append(f"出生于{term_name}前{abs(int(diff_days))}天")
            else:
                # 节气日期早于出生，出生在节气之后
                birth_jie_desc.append(f"出生于{term_name}后{abs(int(diff_days))}天")

    # 节气详情（前后各半年），时间排序与出生节气描述一致
    nearby_terms = []
    for term_name, dt in solar_terms:
        diff_days = (dt - birth_dt_true).total_seconds() / 86400
        if -half_year_days <= diff_days <= half_year_days:
            if diff_days > 0:
                # 节气日期晚于出生：出生在该节气之前
                desc = f"出生于此节气前{abs(int(diff_days))}天"
            else:
                # 节气日期早于出生：出生在该节气之后
                desc = f"出生于此节气后{abs(int(diff_days))}天"
            nearby_terms.append({
                '节气': term_name,
                '时间': dt.strftime('%Y-%m-%d %H:%M'),
                '与出生关系': desc
            })
    nearby_terms = nearby_terms[:24]

    def build_canggan(cg_tuple):
        """藏干格式化：只显示非空，顺序保持主气/中气/余气但不加标签"""
        result_list = [c for c in cg_tuple if c]
        return result_list

    def build_canggan_shishen(cg_shishen_tuple):
        """藏干十神格式化：只显示非空值"""
        result_list = [c for c in cg_shishen_tuple if c]
        return result_list

    def fmt_kongwang(kw: str) -> str:
        """空亡格式化：有则显示具体描述，无则空字符串"""
        return kw  # 已是'空亡'或''

    # 整合结果
    result = {
        '基本信息': {
            '姓名': name,
            '出生时间（公历）': birth_dt.strftime('%Y年%m月%d日 %H时%M分'),
            '真太阳时': birth_dt_true.strftime('%Y年%m月%d日 %H时%M分%S秒'),
            '出生地': location,
            '经度': f"{longitude:.4f}°E",
            '性别': gender,
            '经度时差': f"{(longitude - 120) * 4:.1f}分钟",
        },
        '四柱': {
            '年柱': {
                '干支': year_gz,
                '天干': year_tg,
                '地支': year_dz,
                '天干五行': WUXING_TIAN[TIANGAN.index(year_tg)] if year_tg in TIANGAN else '',
                '地支五行': WUXING_DI[DIZHI.index(year_dz)] if year_dz in DIZHI else '',
                '藏干': build_canggan(year_canggan),
                '天干十神': year_tg_shishen,
                '藏干十神': build_canggan_shishen(year_cg_shishen),
                '星运状态': year_changsheng,
                '自坐状态': year_zizuo,
                '空亡': year_kongwang,
                '纳音': year_nayin,
            },
            '月柱': {
                '干支': month_gz,
                '天干': month_tg,
                '地支': month_dz,
                '天干五行': WUXING_TIAN[TIANGAN.index(month_tg)] if month_tg in TIANGAN else '',
                '地支五行': WUXING_DI[DIZHI.index(month_dz)] if month_dz in DIZHI else '',
                '所在月': f"第{month_index}月（{current_jie[0] if current_jie else '?'}节后）",
                '藏干': build_canggan(month_canggan),
                '天干十神': month_tg_shishen,
                '藏干十神': build_canggan_shishen(month_cg_shishen),
                '星运状态': month_changsheng,
                '自坐状态': month_zizuo,
                '空亡': month_kongwang,
                '纳音': month_nayin,
            },
            '日柱': {
                '干支': day_gz,
                '天干': day_tg,
                '地支': day_dz,
                '天干五行': WUXING_TIAN[TIANGAN.index(day_tg)] if day_tg in TIANGAN else '',
                '地支五行': WUXING_DI[DIZHI.index(day_dz)] if day_dz in DIZHI else '',
                '藏干': build_canggan(day_canggan),
                '天干十神': day_tg_shishen,
                '藏干十神': build_canggan_shishen(day_cg_shishen),
                '星运状态': day_changsheng,
                '自坐状态': day_zizuo,
                '空亡': day_kongwang,
                '纳音': day_nayin,
            },
            '时柱': {
                '干支': hour_gz,
                '天干': hour_tg,
                '地支': hour_dz,
                '天干五行': WUXING_TIAN[TIANGAN.index(hour_tg)] if hour_tg in TIANGAN else '',
                '地支五行': WUXING_DI[DIZHI.index(hour_dz)] if hour_dz in DIZHI else '',
                '时辰': hour_dz + '时',
                '藏干': build_canggan(hour_canggan),
                '天干十神': hour_tg_shishen,
                '藏干十神': build_canggan_shishen(hour_cg_shishen),
                '星运状态': hour_changsheng,
                '自坐状态': hour_zizuo,
                '空亡': hour_kongwang,
                '纳音': hour_nayin,
            },
        },
        '五行统计': wuxing_stats,
        '刑冲合害': xingchonghe,
        '四柱神煞': shensha_sizhu,
        '大运信息': {
            '起运时间': f"{qi_yun_y}岁{qi_yun_m}个月{qi_yun_d}天",
            '顺逆': '顺行' if (gender == '男' and year_tg_idx % 2 == 0) or (gender == '女' and year_tg_idx % 2 == 1) else '逆行',
            '大运列表': dayun_with_shensha,
        },
        '流年信息': {
            '流年干支': liunian_tg_ln + liunian_dz_ln,
            '流年': f"{liunian_year}年（{liunian_year_for_gz}年干支）",
            '神煞': liunian_shensha,
            '刑冲合害': liunian_xingchong,
        },
        '节气信息': {
            '出生节气': birth_jie_desc,
            '节气详情': nearby_terms,
        },
    }

    return result


# ============================================================
# 第七模块：格式化输出
# ============================================================

def print_bazi(result, output_file=None):
    """格式化打印八字排盘结果（JSON格式）

    Args:
        result: 八字计算结果字典
        output_file: 输出文件路径（可选），如果为None则输出到控制台
    """
    import json

    # 确保所有值都是JSON可序列化的
    def make_serializable(obj):
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(v) for v in obj]
        elif isinstance(obj, (tuple)):
            return [make_serializable(v) for v in obj]
        else:
            return obj

    result_serializable = make_serializable(result)
    json_str = json.dumps(result_serializable, ensure_ascii=False, indent=2)

    if output_file:
        # 检查是否为目录，如果是则自动生成文件名
        if os.path.isdir(output_file):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(output_file, f'bazi_result_{timestamp}.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(json_str)
        print(f"结果已保存到: {output_file}")
    else:
        print(json_str)


# ============================================================
# 第八模块：命令行入口
# ============================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='八字排盘计算器 v2.0')
    parser.add_argument('--name', type=str, default='', help='姓名（可选）')
    parser.add_argument('--time', type=str, help='出生时间，格式：YYYY-MM-DD HH:MM')
    parser.add_argument('--location', type=str, default='北京', help='出生地（城市名或经度,纬度）')
    parser.add_argument('--gender', type=str, default='男', choices=['男', '女'], help='性别')
    parser.add_argument('--liunian', type=str, default=None, help='流年年份，格式：YYYY（可选，默认为当前年份）')
    parser.add_argument('--output', type=str, default=None, help='输出文件路径（可选，默认输出到控制台）')
    args = parser.parse_args()

    if args.time:
        result = calculate_bazi(args.time, args.location, args.gender, args.name, args.liunian)
        print_bazi(result, args.output)
    else:
        # 交互模式
        print("=== 八字排盘计算器 v2.0 ===")
        birth_time = input("请输入出生时间（格式：YYYY-MM-DD HH:MM）：").strip()
        location = input("请输入出生地（城市名，如：成都）：").strip() or '北京'
        gender = input("请输入性别（男/女）：").strip() or '男'
        name = input("请输入姓名（留空则不显示）：").strip() or ''
        liunian_input = input("请输入流年年份（格式：YYYY，留空则使用当前年份）：").strip()
        liunian = liunian_input if liunian_input else None
        output_file = input("请输入输出文件路径（留空则输出到控制台）：").strip() or None
        result = calculate_bazi(birth_time, location, gender, name, liunian)
        print_bazi(result, output_file)




