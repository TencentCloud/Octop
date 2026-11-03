# -*- coding: utf-8 -*-
"""生辰八字排盘引擎（bazi-fortune 技能核心脚本）。

用法示例：
    python bazi.py --datetime "1995-06-15 14:30" --gender male --place 武汉 --name 李明天
    python bazi.py --datetime "1995-06-15 14:30" --gender female --lon 114.30 --years 30 --out out.json
    python bazi.py --datetime "1995-06-15" --gender male --hour-scan     # 时辰不定，扫描 12 时辰
    python bazi.py --datetime "1990-05-01 08:00" --gender male --no-tst  # 不做真太阳时校正
    python bazi.py --datetime "..." --gender male --stroke 曦=20 --stroke 梓=11

输出：结构化 JSON（供 LLM 撰写运势报告，或交给 render_report.py 生成 HTML）。
依赖：lunar-python（缺失时自动尝试 pip 安装到隔离 venv）。
"""

import argparse
import datetime as dt
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bazi_data as D  # noqa: E402

WX = ["木", "火", "土", "金", "水"]
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


# ---------------------------------------------------------------- 依赖
def ensure_lunar():
    try:
        from lunar_python import Solar  # noqa
        return True
    except ImportError:
        pass
    py = sys.executable
    try:
        subprocess.run([py, "-m", "pip", "install", "-q", "lunar-python"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        from lunar_python import Solar  # noqa
        return True
    except Exception:
        sys.stderr.write("[错误] 缺少依赖 lunar-python，且自动安装失败。"
                         "请手动执行：pip install lunar-python\n")
        sys.exit(2)


# ---------------------------------------------------------------- 时间与真太阳时
def parse_dt(s):
    s = s.strip().replace("/", "-").replace("年", "-").replace("月", "-").replace("日", " ")
    s = s.replace("时", ":").replace("分", "").replace("T", " ").strip()
    s = " ".join(s.split())
    has_time = ":" in s
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt), has_time
        except ValueError:
            continue
    raise ValueError("无法解析时间：%r（示例：1995-06-15 14:30）" % s)


def in_dst(d):
    """判断中国夏令时区间（1986-1991）"""
    for year, (m1, d1), (m2, d2) in D.DST_RANGES:
        if d.year == year and dt.date(year, m1, d1) <= d.date() <= dt.date(year, m2, d2):
            return True
    return False


def equation_of_time(d):
    """均时差（分钟），低精度近似，误差 < 1 分钟"""
    n = d.timetuple().tm_yday
    b = 2 * math.pi * (n - 81) / 364.0
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def lookup_place(place, lon=None):
    if lon is not None:
        return {"place": place or "自定义", "lon": lon, "source": "用户指定经度"}
    if not place:
        return {"place": "", "lon": 120.0, "source": "未填写地点，默认东经120度（北京时间）"}
    p = place.strip().replace("市", "").replace("县", "").replace("区", "")
    p = p.replace("省", "").replace("特别行政区", "")
    if p in D.CITY_COORD:
        lon, lat = D.CITY_COORD[p]
        return {"place": p, "lon": lon, "lat": lat, "source": "城市坐标表"}
    for city, (clon, clat) in D.CITY_COORD.items():
        if city and city in p:
            return {"place": city + "（由 %s 匹配）" % p, "lon": clon, "lat": clat,
                    "source": "城市模糊匹配"}
    for prov, city in D.PROVINCE_CITY.items():
        if prov and prov in p:
            lon, lat = D.CITY_COORD[city]
            return {"place": city + "（%s 代表城市）" % prov, "lon": lon, "lat": lat,
                    "source": "省级代表城市"}
    return {"place": p, "lon": 120.0,
            "source": "未匹配到坐标，默认东经120度；建议用 --lon 指定经度"}


def true_solar_time(d, lon, use_tst=True, dst_auto=True):
    info = {"beijing_time": d.strftime("%Y-%m-%d %H:%M"), "dst_detected": False}
    bj = d
    if dst_auto and in_dst(d):
        bj = d - dt.timedelta(hours=1)
        info["dst_detected"] = True
        info["dst_note"] = "该日期处于中国夏令时（1986-1991）区间，北京时间已回退 1 小时还原为标准时"
    if not use_tst:
        info.update({"true_solar_time": bj.strftime("%Y-%m-%d %H:%M"), "offset_minutes": 0.0,
                     "lon_diff_min": 0.0, "eot_min": 0.0, "tst_applied": False})
        return bj, info
    lon_diff = (lon - 120.0) * 4.0
    eot = equation_of_time(bj)
    total = lon_diff + eot
    info.update({"lon_diff_min": round(lon_diff, 2), "eot_min": round(eot, 2),
                 "offset_minutes": round(total, 2), "tst_applied": True})
    tst = bj + dt.timedelta(minutes=total)
    info["true_solar_time"] = tst.strftime("%Y-%m-%d %H:%M")
    return tst, info


# ---------------------------------------------------------------- 命理计算
def shishen(day_gan, other_gan):
    a, b = D.GAN_WX[day_gan], D.GAN_WX[other_gan]
    same = D.GAN_YINYANG[day_gan] == D.GAN_YINYANG[other_gan]
    if a == b:
        return "比肩" if same else "劫财"
    if SHENG[b] == a:
        return "偏印" if same else "正印"
    if SHENG[a] == b:
        return "食神" if same else "伤官"
    if KE[b] == a:
        return "七杀" if same else "正官"
    if KE[a] == b:
        return "偏财" if same else "正财"
    return "—"


def branch_coef(zhi, month_zhi):
    """地支五行相对月令的旺相休囚死系数"""
    zw, mw = D.ZHI_WX[zhi], D.ZHI_WX[month_zhi]
    if zw == mw:
        return 1.0, "旺"
    if SHENG[mw] == zw:
        return 0.8, "相"
    if SHENG[zw] == mw:
        return 0.6, "休"
    if KE[zw] == mw:
        return 0.45, "囚"
    return 0.3, "死"


def gan_zhi(g, z):
    return g + z


def build_pillars(b):
    """从 EightChar 对象抽取四柱信息"""
    out = {}
    keys = [("year", "年"), ("month", "月"), ("day", "日"), ("time", "时")]
    for k, cn in keys:
        g = getattr(b, "get%sGan" % k.capitalize())()
        z = getattr(b, "get%sZhi" % k.capitalize())()
        gz = gan_zhi(g, z)
        hide = []
        for cat in ("本气", "中气", "余气"):
            for hg in D.HIDE_GAN[z][cat]:
                hide.append({"gan": hg, "level": cat, "wuxing": D.GAN_WX[hg]})
        out[k] = {
            "label": cn + "柱",
            "gan_zhi": gz,
            "gan": g, "zhi": z,
            "gan_wuxing": D.GAN_WX[g],
            "zhi_wuxing": D.ZHI_WX[z],
            "gan_yinyang": D.GAN_YINYANG[g],
            "zhi_yinyang": D.ZHI_YINYANG[z],
            "na_yin": getattr(b, "get%sNaYin" % k.capitalize())(),
            "di_shi": getattr(b, "get%sDiShi" % k.capitalize())(),
            "di_shi_mean": D.DI_SHI_MEAN.get(getattr(b, "get%sDiShi" % k.capitalize())(), ""),
            "xun_kong": getattr(b, "get%sXunKong" % k.capitalize())(),
            "hide_gan": hide,
        }
    # 十神（以日干为「我」）
    dm = out["day"]["gan"]
    for k in out:
        out[k]["gan_shishen"] = shishen(dm, out[k]["gan"])
        bg = D.HIDE_GAN[out[k]["zhi"]]["本气"][0]
        out[k]["zhi_shishen"] = shishen(dm, bg)
        out[k]["zhi_main_gan"] = bg
        out[k]["gan_shishen_mean"] = D.SHI_SHEN_MEAN.get(out[k]["gan_shishen"], "")
        out[k]["zhi_shishen_mean"] = D.SHI_SHEN_MEAN.get(out[k]["zhi_shishen"], "")
    return out


def wuxing_scores(pillars):
    month_zhi = pillars["month"]["zhi"]
    score = {w: 0.0 for w in WX}
    detail = []
    for k in ("year", "month", "day", "time"):
        z = pillars[k]["zhi"]
        coef, state = branch_coef(z, month_zhi)
        detail.append({"pillar": pillars[k]["label"], "zhi": z, "state": state,
                       "coef": coef, "wuxing": D.ZHI_WX[z]})
        for cat in ("本气", "中气", "余气"):
            for g in D.HIDE_GAN[z][cat]:
                score[D.GAN_WX[g]] += D.HIDE_WEIGHT[cat] * coef
    for k in ("year", "month", "day", "time"):
        g = pillars[k]["gan"]
        w = 1.0
        rooted = any(D.ZHI_WX[pillars[kk]["zhi"]] == D.GAN_WX[g]
                     for kk in ("year", "month", "day", "time"))
        if rooted:
            w += 0.5
        score[D.GAN_WX[g]] += w
    return {w: round(score[w], 2) for w in WX}, detail


def strength_analysis(pillars, scores):
    dm = pillars["day"]["gan"]
    dm_wx = D.GAN_WX[dm]
    sheng_wo = [w for w in WX if SHENG[w] == dm_wx][0]
    wo_sheng = SHENG[dm_wx]
    ke_wo = [w for w in WX if KE[w] == dm_wx][0]
    wo_ke = KE[dm_wx]
    help_s = round(scores[dm_wx] + scores[sheng_wo], 2)
    hurt_s = round(scores[wo_sheng] + scores[wo_ke] + scores[ke_wo], 2)
    ratio = round(help_s / (help_s + hurt_s), 3) if (help_s + hurt_s) else 0.5
    month_zhi = pillars["month"]["zhi"]
    de_ling = D.ZHI_WX[month_zhi] in (dm_wx, sheng_wo)
    # 得令与否为强弱第一要素，做 ±0.05 修正
    adj = round(ratio + (0.05 if de_ling else -0.05), 3)
    if adj >= 0.56:
        verdict = "身旺（偏强）"
    elif adj <= 0.44:
        verdict = "身弱（偏弱）"
    else:
        verdict = "中和"
    if de_ling:
        verdict += "·得令"
    else:
        verdict += "·失令"

    if verdict.startswith("身旺"):
        yongshen = [wo_sheng, wo_ke, ke_wo]
        yongshen_desc = "宜泄、宜耗、宜克：食伤、财星、官杀为用"
        jishen = [dm_wx, sheng_wo]
    elif verdict.startswith("身弱"):
        yongshen = [sheng_wo, dm_wx]
        yongshen_desc = "宜生、宜扶：印星、比劫为用"
        jishen = [wo_sheng, wo_ke, ke_wo]
    else:
        yongshen = [sheng_wo, dm_wx, wo_sheng]
        yongshen_desc = "中和之局，扶抑两可，重在调候与流通"
        jishen = []

    # 调候
    tiao = {"亥": "冬生，寒暖失宜，宜丙火调候", "子": "冬生，寒暖失宜，宜丙火调候",
            "丑": "冬末生，寒土需丙火暖局", "巳": "夏生，火炎土燥，宜壬癸水调候",
            "午": "夏生，火旺极，宜壬水解炎", "未": "夏末生，燥土宜水润",
            "寅": "初春木旺尚寒，宜丙火暖、庚金裁", "卯": "仲春木旺，宜庚金制、丙火暖",
            "辰": "季春湿土，宜丙火暖、甲木疏", "申": "初秋金旺，宜火制金、水泄秀",
            "酉": "仲秋金白水清，宜丁火锻炼", "戌": "季秋燥土，宜水润、甲木疏"}
    return {
        "day_master": dm, "day_master_wuxing": dm_wx,
        "day_master_yinyang": D.GAN_YINYANG[dm],
        "help_score": help_s, "hurt_score": hurt_s, "ratio": ratio,
        "ratio_adjusted": adj,
        "de_ling": de_ling, "month_ling": month_zhi,
        "month_ling_wuxing": D.ZHI_WX[month_zhi],
        "verdict": verdict,
        "yongshen_wuxing": yongshen, "yongshen_desc": yongshen_desc,
        "jishen_wuxing": jishen,
        "tiaohou": tiao.get(month_zhi, ""),
        "relations": {"同我(比劫)": dm_wx, "生我(印)": sheng_wo, "我生(食伤)": wo_sheng,
                      "我克(财)": wo_ke, "克我(官杀)": ke_wo},
    }


def collect_shensha(pillars, b=None):
    """常用神煞：以日干/年干查四支，或按年支/日支三合局诀查四支"""
    dm = pillars["day"]["gan"]
    yg = pillars["year"]["gan"]
    yz = pillars["year"]["zhi"]
    dz = pillars["day"]["zhi"]
    zhis = {"年支": pillars["year"]["zhi"], "月支": pillars["month"]["zhi"],
            "日支": pillars["day"]["zhi"], "时支": pillars["time"]["zhi"]}
    res = []

    def add(name, hits):
        if hits:
            res.append({"name": name, "hits": hits, "meaning": D.SHEN_SHA_MEAN.get(name, "")})

    gan_tables = [
        ("天乙贵人", D.TIAN_YI, [dm, yg]), ("太极贵人", D.TAI_JI, [dm, yg]),
        ("文昌贵人", D.WEN_CHANG, [dm]), ("国印贵人", D.GUO_YIN, [dm]),
        ("羊刃", D.YANG_REN, [dm]), ("禄神", D.LU_SHEN, [dm]), ("金舆", D.JIN_YU, [dm]),
    ]
    for name, table, gans in gan_tables:
        hits = []
        for g in gans:
            if g not in table:
                continue
            for p, z in zhis.items():
                if z in table[g]:
                    tag = "%s(%s)" % (z, p)
                    if tag not in hits:
                        hits.append(tag)
        add(name, hits)

    zhi_tables = ["驿马", "桃花", "华盖", "将星", "劫煞", "亡神"]
    for name in zhi_tables:
        hits = []
        for base, blabel in ((yz, "年支"), (dz, "日支")):
            target = D.SANHE_TARGET[base][name]
            if target in zhis.values():
                p = [k for k, v in zhis.items() if v == target]
                tag = "%s(%s)" % (target, "/".join(p))
                if tag not in hits:
                    hits.append(tag)
        add(name, hits)

    if D.GU_CHEN[yz] in zhis.values():
        add("孤辰", [D.GU_CHEN[yz]])
    if D.GUA_SU[yz] in zhis.values():
        add("寡宿", [D.GUA_SU[yz]])

    if pillars["day"]["gan_zhi"] in ("庚辰", "庚戌", "壬辰", "戊戌"):
        add("魁罡", [pillars["day"]["gan_zhi"] + "(日柱)"])

    ny = pillars["year"]["na_yin"][-1]
    if ny in ("火",) and ("戌" in zhis.values() or "亥" in zhis.values()):
        add("天罗地网", ["火命见戌亥"])
    if ny in ("水", "土") and ("辰" in zhis.values() or "巳" in zhis.values()):
        add("天罗地网", ["水土命见辰巳"])
    return res


def find_interactions(pillars):
    zs = [("年支", pillars["year"]["zhi"]), ("月支", pillars["month"]["zhi"]),
          ("日支", pillars["day"]["zhi"]), ("时支", pillars["time"]["zhi"])]
    vals = [z for _, z in zs]
    out = []
    for i in range(len(zs)):
        for j in range(i + 1, len(zs)):
            a, b = zs[i][1], zs[j][1]
            if D.LIU_HE.get(a) == b:
                out.append({"type": "六合", "pair": a + b, "a": zs[i][0], "b": zs[j][0],
                            "note": "合中有情，主牵绊与和解"})
            if D.LIU_CHONG.get(a) == b:
                out.append({"type": "六冲", "pair": a + b, "a": zs[i][0], "b": zs[j][0],
                            "note": "冲主动变、分离、突发"})
            if D.LIU_HAI.get(a) == b:
                out.append({"type": "六害", "pair": a + b, "a": zs[i][0], "b": zs[j][0],
                            "note": "害主暗损、六亲不睦"})
            if D.LIU_PO.get(a) == b:
                out.append({"type": "相破", "pair": a + b, "a": zs[i][0], "b": zs[j][0],
                            "note": "破主破坏、散耗"})
    for grp in D.SAN_HE:
        a, b, c, wx = grp
        present = [x for x in (a, b, c) if x in vals]
        if len(present) == 3:
            out.append({"type": "三合局", "pair": a + b + c, "a": "-", "b": "-",
                        "note": "合成 %s局，力量显著增强" % wx})
        elif b in vals and len(present) == 2:
            out.append({"type": "半合", "pair": "".join(present), "a": "-", "b": "-",
                        "note": "%s局半合，力量次于全合" % wx})
        elif b not in vals and len(present) == 2:
            out.append({"type": "拱合", "pair": "".join(present), "a": "-", "b": "-",
                        "note": "%s局拱合，待岁运填实" % wx})
    for grp in D.SAN_HUI:
        a, b, c, wx = grp
        if a in vals and b in vals and c in vals:
            out.append({"type": "三会方", "pair": a + b + c, "a": "-", "b": "-",
                        "note": "会成 %s方，气势专旺" % wx})
    for a, b, c, nm in D.SAN_XING:
        if c:
            if a in vals and b in vals and c in vals:
                out.append({"type": "三刑", "pair": a + b + c, "a": "-", "b": "-", "note": nm})
        elif a in vals and b in vals:
            out.append({"type": "无礼之刑", "pair": a + b, "a": "-", "b": "-", "note": nm})
    zx_dup = [z for z in set(vals) if vals.count(z) >= 2 and z in D.ZI_XING]
    if zx_dup:
        out.append({"type": "自刑", "pair": "".join(zx_dup * 2), "a": "-", "b": "-",
                    "note": "自刑主内耗、自我纠结，凡事易自我设限"})
    return out


def liunian_hits(zhi, pillars):
    """流年支与命局四支的关系"""
    zs = {"年支": pillars["year"]["zhi"], "月支": pillars["month"]["zhi"],
          "日支": pillars["day"]["zhi"], "时支": pillars["time"]["zhi"]}
    hits = []
    for p, z in zs.items():
        if D.LIU_CHONG.get(zhi) == z:
            hits.append("冲" + p)
        if D.LIU_HE.get(zhi) == z:
            hits.append("合" + p)
        if D.LIU_HAI.get(zhi) == z:
            hits.append("害" + p)
        if D.LIU_PO.get(zhi) == z:
            hits.append("破" + p)
    return hits


def build_dayun(b, gender, pillars, from_year, to_year):
    yun = b.getYun(1 if gender == "male" else 0)
    start = {"start_year": yun.getStartYear(), "start_month": yun.getStartMonth(),
             "start_day": yun.getStartDay(), "forward": yun.isForward(),
             "start_solar": yun.getStartSolar().toYmd()}
    items = []
    for d in yun.getDaYun():
        gz = d.getGanZhi()
        if not gz:
            continue
        if d.getStartYear() > to_year:
            break
        entry = {
            "index": d.getIndex() or 0,
            "gan_zhi": gz,
            "gan": gz[0], "zhi": gz[1],
            "start_age": d.getStartAge(), "end_age": d.getEndAge(),
            "start_year": d.getStartYear(), "end_year": d.getEndYear(),
            "xun_kong": d.getXunKong(),
            "gan_shishen": shishen(pillars["day"]["gan"], gz[0]),
            "zhi_shishen": shishen(pillars["day"]["gan"], D.HIDE_GAN[gz[1]]["本气"][0]),
            "na_yin": D.NA_YIN.get(gz, ""),
        }
        ln = []
        for x in d.getLiuNian():
            y = x.getYear()
            if y < from_year or y > to_year:
                continue
            lgz = x.getGanZhi()
            ln.append({
                "year": y, "age": x.getAge(), "gan_zhi": lgz,
                "gan": lgz[0], "zhi": lgz[1],
                "gan_shishen": shishen(pillars["day"]["gan"], lgz[0]),
                "zhi_shishen": shishen(pillars["day"]["gan"], D.HIDE_GAN[lgz[1]]["本气"][0]),
                "na_yin": D.NA_YIN.get(lgz, ""),
                "xun_kong": x.getXunKong(),
                "hits": liunian_hits(lgz[1], pillars),
                "fan_taisui": D.LIU_CHONG.get(lgz[1]) == pillars["year"]["zhi"],
                "ben_ming_nian": lgz[1] == pillars["year"]["zhi"],
            })
        entry["liu_nian"] = ln
        if ln or d.getStartYear() >= from_year - 1:
            items.append(entry)
    return start, items


# ---------------------------------------------------------------- 姓名
def num_wuxing(n):
    m = n % 10
    return {1: "木", 2: "木", 3: "火", 4: "火", 5: "土",
            6: "土", 7: "金", 8: "金", 9: "水", 0: "水"}[m]


def wuge_info(n):
    if n <= 0:
        return {"num": n, "level": "—", "desc": "—"}
    lv, desc = D.WUGE_JIXIONG.get(n, ("—", "超出常用数理范围"))
    return {"num": n, "level": lv, "desc": desc, "wuxing": num_wuxing(n)}


def name_analysis(name, yongshen, stroke_override=None):
    if not name:
        return None
    override = stroke_override or {}
    chars = [c for c in name if c.strip()]
    missing = []
    strokes = []
    for c in chars:
        if c in override:
            strokes.append(override[c])
        elif c in D.KANGXI_STROKES:
            strokes.append(D.KANGXI_STROKES[c])
        else:
            strokes.append(None)
            missing.append(c)
    if None in strokes:
        return {"name": name, "chars": chars, "strokes": strokes,
                "missing_chars": missing,
                "error": "部分字的康熙笔画缺失，五格无法计算。"
                         "可用 --stroke 字=数字 手工指定，或人工核对《康熙字典》。"}
    surname_len = 1
    common_two = ["欧阳", "司马", "上官", "诸葛", "东方", "独孤", "慕容", "尉迟",
                  "长孙", "呼延", "淳于", "夏侯", "万俟", "澹台", "皇甫", "令狐"]
    for s in common_two:
        if name.startswith(s):
            surname_len = 2
            break
    s_strokes = strokes[:surname_len]
    g_strokes = strokes[surname_len:]
    if not g_strokes:
        return {"name": name, "error": "未提供名字部分（需至少 1 个名用字）"}
    tian = sum(s_strokes) + (0 if surname_len == 2 else 1)
    ren = s_strokes[-1] + g_strokes[0]
    di = sum(g_strokes) + (1 if len(g_strokes) == 1 else 0)
    zong = sum(strokes)
    wai = zong - ren
    sancai = num_wuxing(tian) + num_wuxing(ren) + num_wuxing(di)
    name_wx = [D.CHAR_WX_HINT.get(c, "") for c in chars]
    match = [w for w in name_wx if w in (yongshen or [])]
    return {
        "name": name, "surname_len": surname_len,
        "chars": [{"char": c, "stroke": s, "wuxing_hint": D.CHAR_WX_HINT.get(c, "")}
                  for c, s in zip(chars, strokes)],
        "wuge": {"天格": wuge_info(tian), "人格": wuge_info(ren),
                 "地格": wuge_info(di), "外格": wuge_info(wai), "总格": wuge_info(zong)},
        "sancai": sancai,
        "sancai_good": sancai in D.SANCAI_GOOD,
        "name_wuxing": [w for w in name_wx if w],
        "match_yongshen": match,
        "match_comment": ("名字五行 %s 与喜用神 %s 相合，有助补益"
                          % ("、".join(sorted(set(match))), "、".join(yongshen or []))
                          if match else
                          "名字五行（%s）与喜用神（%s）不合，补益有限，可作为参考而非决定因素"
                          % ("、".join(sorted(set(name_wx) - {""})) or "未识别",
                             "、".join(yongshen or []))),
    }


# ---------------------------------------------------------------- 主流程
def compute(args):
    from lunar_python import Solar

    base, has_time = parse_dt(args.datetime)
    if not has_time:
        base = base.replace(hour=12, minute=0)
    place = lookup_place(args.place, args.lon)
    tst, tinfo = true_solar_time(base, place["lon"], not args.no_tst, not args.no_dst)

    solar = Solar.fromYmdHms(tst.year, tst.month, tst.day, tst.hour, tst.minute, 0)
    lunar = solar.getLunar()
    b = lunar.getEightChar()

    pillars = build_pillars(b)
    scores, detail = wuxing_scores(pillars)
    strength = strength_analysis(pillars, scores)
    shensha = collect_shensha(pillars, b)
    inter = find_interactions(pillars)
    this_year = dt.date.today().year
    from_year = args.from_year or solar.getYear()
    to_year = args.to_year or (this_year + args.years)
    yun_start, dayun = build_dayun(b, args.gender, pillars, from_year, to_year)

    counts = {w: 0 for w in WX}
    for k in ("year", "month", "day", "time"):
        counts[D.GAN_WX[pillars[k]["gan"]]] += 1
        counts[D.ZHI_WX[pillars[k]["zhi"]]] += 1
    missing = [w for w in WX if counts[w] == 0]

    nm = name_analysis(args.name, strength["yongshen_wuxing"], args.stroke)

    result = {
        "meta": {
            "gender": args.gender, "name": args.name,
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "engine": "lunar-python 干支历 + 本地神煞/十神/力量评分规则",
            "hour_known": has_time,
        },
        "input": {"datetime_raw": args.datetime, "place_raw": args.place},
        "place": place,
        "time_correction": tinfo,
        "solar": solar.toYmdHms(),
        "lunar": {
            "year_cn": lunar.getYearInChinese() + "年",
            "month_cn": lunar.getMonthInChinese() + "月",
            "day_cn": lunar.getDayInChinese(),
            "gan_zhi_year": lunar.getYearInGanZhi(),
            "sheng_xiao": lunar.getYearShengXiao(),
            "lei_month": lunar.getMonth(),
            "description": lunar.toString(),
        },
        "pillars": pillars,
        "strength": strength,
        "wuxing": {"counts": counts, "scores": scores, "missing": missing,
                   "branch_state": detail},
        "shensha": shensha,
        "interactions": inter,
        "dayun_start": yun_start,
        "dayun": dayun,
        "extra": {"tai_yuan": b.getTaiYuan(), "ming_gong": b.getMingGong(),
                  "shen_gong": b.getShenGong(),
                  "tai_yuan_na_yin": b.getTaiYuanNaYin(),
                  "ming_gong_na_yin": b.getMingGongNaYin()},
        "name_analysis": nm,
        "events": args.event or [],
        "family": args.family or "",
    }
    return result, solar, tst, place


def hour_scan(args):
    from lunar_python import Solar
    base, _ = parse_dt(args.datetime)
    base = base.replace(hour=0, minute=0)
    place = lookup_place(args.place, args.lon)
    rows = []
    names = ["子(23-1)", "丑(1-3)", "寅(3-5)", "卯(5-7)", "辰(7-9)", "巳(9-11)",
             "午(11-13)", "未(13-15)", "申(15-17)", "酉(17-19)", "戌(19-21)", "亥(21-23)"]
    for i, nm in enumerate(names):
        hh = 0 if i == 0 else i * 2
        d = base + dt.timedelta(hours=hh)
        t, _ = true_solar_time(d, place["lon"], not args.no_tst, not args.no_dst)
        s = Solar.fromYmdHms(t.year, t.month, t.day, t.hour, t.minute, 0)
        b = s.getLunar().getEightChar()
        rows.append({
            "hour_name": nm, "hour_range": nm.split("(")[1].rstrip(")"),
            "beijing_time": d.strftime("%Y-%m-%d %H:%M"),
            "true_solar": t.strftime("%Y-%m-%d %H:%M"),
            "day_gz": b.getDay(),
            "time_gz": b.getTime(),
            "time_wuxing": b.getTimeWuXing(),
            "time_shishen": b.getTimeShiShenGan(),
            "time_na_yin": b.getTimeNaYin(),
            "time_di_shi": b.getTimeDiShi(),
        })
    return {"scan": rows, "place": place,
            "note": "时辰不定时的十二时辰比对表：请用已知人生事件（升学/工作/婚恋/伤病/迁居的年份与性质）"
                    "对照各时辰命局与大运流年，选取最吻合者定盘。",
            "zi_note": "子时跨日：若 day_gz 与当日日柱不同，说明该时辰为「晚子时」，日柱按次日推算（本表已自动处理）。"}


def text_summary(r):
    p = r["pillars"]
    s = r["strength"]
    lines = []
    lines.append("=" * 56)
    lines.append("八字：%s  %s  %s  %s" % (p["year"]["gan_zhi"], p["month"]["gan_zhi"],
                                           p["day"]["gan_zhi"], p["time"]["gan_zhi"]))
    lines.append("十神：%s  %s  日主  %s" % (p["year"]["gan_shishen"], p["month"]["gan_shishen"],
                                            p["time"]["gan_shishen"]))
    lines.append("纳音：%s / %s / %s / %s" % (p["year"]["na_yin"], p["month"]["na_yin"],
                                              p["day"]["na_yin"], p["time"]["na_yin"]))
    lines.append("日主：%s（%s·%s） 生于%s月（%s）" %
                 (s["day_master"], s["day_master_wuxing"], s["day_master_yinyang"],
                  s["month_ling"], s["month_ling_wuxing"]))
    lines.append("强弱：%s（助%.2f / 耗%.2f，比值%.3f→%.3f）" %
                 (s["verdict"], s["help_score"], s["hurt_score"], s["ratio"],
                  s.get("ratio_adjusted", s["ratio"])))
    lines.append("喜用：%s | 忌：%s" % ("、".join(s["yongshen_wuxing"]),
                                       "、".join(s["jishen_wuxing"]) or "—"))
    lines.append("五行：%s" % "  ".join("%s%d" % (w, r["wuxing"]["counts"][w]) for w in WX))
    lines.append("神煞：%s" % ("、".join(x["name"] for x in r["shensha"]) or "无明显神煞"))
    lines.append("起运：%d年%d月%d日后起运（%s）" %
                 (r["dayun_start"]["start_year"], r["dayun_start"]["start_month"],
                  r["dayun_start"]["start_day"],
                  "顺排" if r["dayun_start"]["forward"] else "逆排"))
    for d in r["dayun"][:8]:
        lines.append("  %2d-%2d岁(%d-%d) %s %s" %
                     (d["start_age"], d["end_age"], d["start_year"], d["end_year"],
                      d["gan_zhi"], d["gan_shishen"]))
    lines.append("=" * 56)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="生辰八字排盘与运势分析引擎")
    ap.add_argument("--datetime", required=True, help="出生时间，如 1995-06-15 14:30")
    ap.add_argument("--gender", default="male", choices=["male", "female"], help="性别")
    ap.add_argument("--place", default="", help="出生地，如 武汉 / 广东省 / 台北市")
    ap.add_argument("--lon", type=float, default=None, help="出生地经度（东经为正），优先于城市匹配")
    ap.add_argument("--name", default="", help="姓名（用于五格与五行补益分析）")
    ap.add_argument("--event", action="append", default=[],
                    help="人生事件，格式 年份:描述，可重复，如 2014:考上大学")
    ap.add_argument("--family", default="", help="家庭条件/成长背景描述")
    ap.add_argument("--years", type=int, default=30, help="向后推算年数，默认 30")
    ap.add_argument("--from-year", type=int, default=None)
    ap.add_argument("--to-year", type=int, default=None)
    ap.add_argument("--hour-scan", action="store_true", help="时辰不定：扫描十二时辰")
    ap.add_argument("--no-tst", action="store_true", help="不做真太阳时校正")
    ap.add_argument("--no-dst", action="store_true", help="不做夏令时回退")
    ap.add_argument("--stroke", action="append", default=[], help="手工指定康熙笔画，如 曦=20")
    ap.add_argument("--out", default=None, help="JSON 输出文件路径")
    ap.add_argument("--text", action="store_true", help="额外打印文本摘要到 stderr")
    args = ap.parse_args()

    args.stroke = {k: int(v) for k, v in (s.split("=") for s in args.stroke)}
    ensure_lunar()

    if args.hour_scan:
        r = hour_scan(args)
    else:
        r, _, _, _ = compute(args)
        if args.text:
            sys.stderr.write(text_summary(r) + "\n")
    data = json.dumps(r, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(data)
        sys.stderr.write("已写入 %s\n" % args.out)
    else:
        print(data)


if __name__ == "__main__":
    main()
