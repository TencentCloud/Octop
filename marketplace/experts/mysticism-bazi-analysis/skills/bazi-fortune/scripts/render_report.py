# -*- coding: utf-8 -*-
"""把 bazi.py 输出的 JSON 渲染成可视化命理报告 HTML。

用法：
    python render_report.py chart.json -o report.html
    python render_report.py chart.json -n narrative.json -o report.html

narrative.json 为 LLM 撰写的文字点评，键见 NARRATIVE_KEYS（缺省则留空）。
"""

import argparse
import datetime as dt
import json
import os

WX_COLOR = {"木": "var(--mu)", "火": "var(--huo)", "土": "var(--tu)",
            "金": "var(--jin)", "水": "var(--shui)"}
WX_ORDER = ["木", "火", "土", "金", "水"]

NARRATIVE_KEYS = [
    ("summary", "命局总评"),
    ("personality", "性格与天赋"),
    ("career", "事业与财运"),
    ("love", "婚姻与感情"),
    ("health", "健康与养生"),
    ("family", "家庭与早年环境"),
    ("name", "姓名点评"),
    ("events", "过往事件复盘与定盘"),
    ("forecast", "未来运势详批"),
    ("advice", "开运建议"),
]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if s is not None else "")


def pillar_card(p):
    hide = "、".join("%s(%s)" % (h["gan"], h["level"]) for h in p["hide_gan"])
    return f"""
      <div class="pillar">
        <div class="p-label">{esc(p['label'])}</div>
        <div class="p-gan" style="color:{WX_COLOR[p['gan_wuxing']]}">{esc(p['gan'])}</div>
        <div class="p-zhi" style="color:{WX_COLOR[p['zhi_wuxing']]}">{esc(p['zhi'])}</div>
        <div class="p-ss">{esc(p['gan_shishen'])}</div>
        <div class="p-meta">
          纳音 {esc(p['na_yin'])}<br>
          星运 {esc(p['di_shi'])}<br>
          空亡 {esc(p['xun_kong']) or '—'}
          <div class="p-hide">藏干：{esc(hide)}</div>
        </div>
      </div>"""


def wuxing_bars(wx):
    scores = wx["scores"]
    mx = max(scores.values()) or 1
    rows = []
    for w in WX_ORDER:
        pct = int(scores[w] / mx * 100)
        rows.append(
            f'<div class="wxbar"><span class="nm">{w}</span>'
            f'<span class="track"><span class="fill" style="width:{pct}%;'
            f'background:{WX_COLOR[w]}"></span></span>'
            f'<span class="num">{wx["counts"][w]}个 / {scores[w]}分</span></div>')
    miss = "、".join(wx["missing"]) or "五行齐全"
    rows.append(f'<p style="margin-top:10px;font-size:13px;color:var(--ink3)">'
                f'五行缺失：{esc(miss)}</p>')
    return "".join(rows)


def dayun_table(dayun):
    rows = []
    for d in dayun:
        ln = d.get("liu_nian", [])
        ln_txt = []
        for x in ln:
            marks = "".join(x["hits"])
            flag = ""
            if x["ben_ming_nian"]:
                flag = " <span class='tag warn'>本命年</span>"
            elif x["fan_taisui"]:
                flag = " <span class='tag bad'>冲太岁</span>"
            ln_txt.append(f"{x['year']}（{x['age']}岁）{x['gan_zhi']} {x['gan_shishen']}"
                          + (f" · {esc(marks)}" if marks else "") + flag)
        rows.append(
            f"<tr><td>{d['start_age']}-{d['end_age']}岁</td>"
            f"<td>{d['start_year']}-{d['end_year']}</td>"
            f"<td style='font-size:15px'><b>{esc(d['gan_zhi'])}</b></td>"
            f"<td>{esc(d['gan_shishen'])}</td>"
            f"<td>{esc(d['zhi_shishen'])}</td>"
            f"<td style='text-align:left;font-size:12.5px'>"
            + ("<br>".join(ln_txt) if ln_txt else "<span class='empty'>—</span>")
            + "</td></tr>")
    return ("<table><thead><tr><th>大运</th><th>年份</th><th>干支</th><th>天干十神</th>"
            "<th>地支十神</th><th>流年（干支·十神·与命局关系）</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def narr(n, key):
    v = n.get(key, "")
    return f'<div class="narr">{esc(v)}</div>' if v else ""


def build_body(c, n):
    p = c["pillars"]
    s = c["strength"]
    tc = c["time_correction"]
    out = []
    out.append(f"""
    <header>
      <h1>生辰八字命理报告</h1>
      <div class="sub">{esc(c.get('meta', {}).get('name') or '匿名')} ·
        {'男' if c['meta']['gender'] == 'male' else '女'} ·
        {esc(c['input']['datetime_raw'])} · {esc(c.get('place', {}).get('place') or '地点未填')}</div>
      <div class="sub">生成于 {esc(c['meta']['generated_at'])}</div>
    </header>""")

    # 1 基本信息
    tst_note = ""
    if tc.get("tst_applied"):
        tst_note = (f"真太阳时 {esc(tc['true_solar_time'])}"
                    f"（经度差 {tc['lon_diff_min']} 分 · 均时差 {tc['eot_min']} 分）")
    else:
        tst_note = "未做真太阳时校正"
    if tc.get("dst_detected"):
        tst_note += " · <b>已回退夏令时 1 小时</b>"
    if not c["meta"]["hour_known"]:
        tst_note += " · <b>时辰未知，时柱按推测填入，务必核实</b>"
    out.append(f"""
    <section>
      <h2>一 · 基本信息与定时</h2>
      <div class="kv">
        <div><b>公历</b>{esc(c['solar'])}</div>
        <div><b>农历</b>{esc(c['lunar']['description'])}</div>
        <div><b>生肖</b>{esc(c['lunar']['sheng_xiao'])}</div>
        <div><b>出生地</b>{esc(c.get('place', {}).get('place') or '—')}
            （东经 {esc(c.get('place', {}).get('lon'))}°）</div>
        <div><b>校正</b>{tst_note}</div>
        <div><b>起运</b>{esc(c['dayun_start']['start_year'])}年{esc(c['dayun_start']['start_month'])}月
            {esc(c['dayun_start']['start_day'])}日后起运，
            {'顺排' if c['dayun_start']['forward'] else '逆排'}</div>
      </div>
      {narr(n, 'events')}
    </section>""")

    # 2 命盘
    out.append(f"""
    <section>
      <h2>二 · 四柱命盘</h2>
      <div class="pillars">{"".join(pillar_card(p[k]) for k in ("year", "month", "day", "time"))}</div>
      <p style="text-align:center;color:var(--ink3);font-size:12.5px;margin-top:10px">
        {esc(p['year']['gan_zhi'])}　{esc(p['month']['gan_zhi'])}　{esc(p['day']['gan_zhi'])}　{esc(p['time']['gan_zhi'])}
        　｜　胎元 {esc(c['extra']['tai_yuan'])}　命宫 {esc(c['extra']['ming_gong'])}　身宫 {esc(c['extra']['shen_gong'])}
      </p>
      {narr(n, 'summary')}
    </section>""")

    # 3 日主与格局
    yong = "、".join(s["yongshen_wuxing"])
    ji = "、".join(s["jishen_wuxing"]) or "—"
    out.append(f"""
    <section>
      <h2>三 · 日主强弱与喜用神</h2>
      <div class="kv">
        <div><b>日主</b>{esc(s['day_master'])}（{esc(s['day_master_wuxing'])}·{esc(s['day_master_yinyang'])}）</div>
        <div><b>月令</b>{esc(s['month_ling'])}月（{esc(s['month_ling_wuxing'])}）</div>
        <div><b>格局判定</b>{esc(s['verdict'])}</div>
        <div><b>力量比</b>助 {s['help_score']} / 耗 {s['hurt_score']}，
            比值 {s['ratio']}（校正后 {s.get('ratio_adjusted', s['ratio'])}）</div>
        <div><b>喜用神</b><span class="tag good">{esc(yong)}</span></div>
        <div><b>忌神</b><span class="tag bad">{esc(ji)}</span></div>
        <div><b>调候</b>{esc(s['tiaohou'])}</div>
      </div>
      {narr(n, 'personality')}
    </section>""")

    # 4 五行
    out.append(f"""
    <section>
      <h2>四 · 五行分布</h2>
      {wuxing_bars(c['wuxing'])}
    </section>""")

    # 5 神煞与刑冲合害
    ss = "".join('<span class="tag">%s（%s）</span>' % (esc(x["name"]), esc("、".join(x["hits"])))
                 for x in c.get("shensha", [])) or '<span class="empty">命局无明显常用神煞</span>'
    it = "".join('<span class="tag %s">%s：%s·%s</span>' % (
        "bad" if x["type"] in ("六冲", "三刑", "无礼之刑", "自刑", "六害") else
        "good" if x["type"] in ("六合", "三合局", "三会方") else "",
        esc(x["type"]), esc(x["pair"]),
        esc(x["a"] + "—" + x["b"]) if x["a"] != "-" else esc(x["note"][:14]))
                 for x in c.get("interactions", [])) or '<span class="empty">四支无明显刑冲合害</span>'
    out.append(f"""
    <section>
      <h2>五 · 神煞与地支关系</h2>
      <h3>神煞</h3><div>{ss}</div>
      <h3>刑冲合害</h3><div>{it}</div>
      {narr(n, 'family')}
    </section>""")

    # 6 大运流年
    out.append(f"""
    <section>
      <h2>六 · 大运与流年</h2>
      {dayun_table(c.get('dayun', []))}
      {narr(n, 'forecast')}
    </section>""")

    # 7 分项运势
    out.append(f"""
    <section>
      <h2>七 · 分项详批</h2>
      <h3>事业与财运</h3>{narr(n, 'career')}
      <h3>婚姻与感情</h3>{narr(n, 'love')}
      <h3>健康与养生</h3>{narr(n, 'health')}
    </section>""")

    # 8 姓名
    nm = c.get("name_analysis")
    if nm:
        if nm.get("error"):
            body = f'<p class="empty">{esc(nm["error"])}</p>'
        else:
            wg = nm["wuge"]
            body = ("<table><thead><tr><th>格局</th><th>数理</th><th>五行</th>"
                    "<th>吉凶</th><th>含义</th></tr></thead><tbody>"
                    + "".join(f"<tr><td>{k}</td><td>{v['num']}</td><td>{v.get('wuxing','')}</td>"
                              f"<td>{esc(v['level'])}</td><td style='text-align:left'>"
                              f"{esc(v['desc'])}</td></tr>"
                              for k, v in wg.items())
                    + "</tbody></table>"
                    + f'<p style="margin-top:10px">三才配置：<b>{esc(nm["sancai"])}</b>'
                      f'（{"吉" if nm["sancai_good"] else "需谨慎"}）｜'
                      f'名字五行：{esc("、".join(nm["name_wuxing"]) or "未识别")}<br>'
                      f'{esc(nm["match_comment"])}</p>')
        out.append(f'<section><h2>八 · 姓名分析</h2>{body}{narr(n, "name")}</section>')

    # 9 建议
    out.append(f"""
    <section>
      <h2>九 · 开运建议</h2>
      {narr(n, 'advice')}
    </section>""")

    out.append(f"""
    <footer>
      <div class="disc">
        本报告由「bazi-fortune 生辰八字排盘与运势分析」技能生成，
        排盘算法基于干支历（含真太阳时校正、夏令时还原），
        文字解读综合传统子平命理规则生成。<br>
        命理属于传统文化与民俗参考范畴，不构成任何医疗、法律、投资、择业或人生重大决策的建议。
        请理性看待，以现实行动与专业意见为准。
      </div>
      <div style="margin-top:12px">生成时间 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
    </footer>""")
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description="八字报告 HTML 渲染器")
    ap.add_argument("chart", help="bazi.py 输出的 JSON 文件")
    ap.add_argument("-n", "--narrative", default=None, help="LLM 文字点评 JSON 文件")
    ap.add_argument("-o", "--out", default="bazi_report.html")
    ap.add_argument("--title", default="生辰八字命理报告")
    args = ap.parse_args()

    with open(args.chart, encoding="utf-8") as f:
        c = json.load(f)
    n = {}
    if args.narrative:
        with open(args.narrative, encoding="utf-8") as f:
            n = json.load(f)

    tpl_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "assets", "report_template.html")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()

    html = tpl.replace("{{TITLE}}", esc(args.title)).replace("{{BODY}}", build_body(c, n))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成 %s" % args.out)
    print("narrative 可用键：" + "、".join(k for k, _ in NARRATIVE_KEYS))


if __name__ == "__main__":
    main()
